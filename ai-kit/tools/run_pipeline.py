#!/usr/bin/env python3
"""Bounded local Codex build/test/fresh-review loop. Python 3.10+, Linux/WSL/macOS.

This is an orchestration helper, not a security sandbox. It executes generated test
scripts directly. Use only in a disposable development VM with no production secrets.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

PHASES = ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "FINAL"]
PROMPTS = ["01_M0_CONTRACT_AND_PLAN.md", "02_M1_FOUNDATION.md", "03_M2_ADMISSION.md",
           "04_M3_ENGINE.md", "05_M4_ADAPTERS.md", "06_M5_RECOVERY.md", "07_M6_DELIVERY.md",
           "08_FINAL_ACCEPTANCE.md"]
IGNORED = {".git", ".ai-run", ".evidence", "target", "build", "node_modules", "__pycache__",
           ".pytest_cache", ".venv", ".tools", ".cache", ".local", ".m2", ".gradle"}

class PipelineError(RuntimeError):
    pass

def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PipelineError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Expected JSON object: {path}")
    return value

def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

def source_fingerprint(root: Path) -> str:
    """Hash source/config/docs, not test outputs, Git metadata or workspace caches."""
    h = hashlib.sha256()
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in sorted(files):
            p = Path(current) / name
            if p.is_symlink():
                payload = ("SYMLINK:" + os.readlink(p)).encode()
            elif p.is_file():
                payload = p.read_bytes()
            else:
                continue
            h.update(p.relative_to(root).as_posix().encode() + b"\0")
            h.update(hashlib.sha256(payload).digest())
    return h.hexdigest()

def protected_files(root: Path) -> dict[str, str]:
    manifest = root / "ai-kit/CHECKSUMS.sha256"
    if not manifest.is_file():
        raise PipelineError("Missing protected kit checksum manifest")
    expected = {}
    for line in manifest.read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise PipelineError(f"Missing/symlinked protected file: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise PipelineError(f"Protected kit changed: {name}")
        expected[name] = digest
    expected["ai-kit/CHECKSUMS.sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return expected

def check_protected(root: Path, expected: dict[str, str]) -> None:
    for name, digest in expected.items():
        p = root / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise PipelineError(f"Protected baseline modified: {name}; refusing to continue")

def safe_evidence(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PipelineError("Evidence path must be a nonempty relative path")
    rel = Path(relative)
    p = (base / rel).resolve()
    if rel.is_absolute() or not p.is_relative_to(base.resolve()):
        raise PipelineError(f"Evidence escapes directory: {relative}")
    if not p.is_file() or p.stat().st_size == 0:
        raise PipelineError(f"Missing/empty evidence: {relative}")
    return p

def required_for(requirements: dict, phase: str, mode: str) -> set[str]:
    index = PHASES.index(phase)
    return {r["id"] for r in requirements["requirements"]
            if PHASES.index(r["phase"]) <= index and r["verification_mode"] == mode}

def junit_counts(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PipelineError(f"Invalid JUnit XML: {path}: {exc}") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise PipelineError(f"Not a JUnit report: {path}")
    cases = list(root.iter("testcase"))
    result = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    for case in cases:
        for key, tag in [("failures", "failure"), ("errors", "error"), ("skipped", "skipped")]:
            result[key] += int(case.find(tag) is not None)
    # Surface suite-level errors even if a crashed runner emitted no testcase.
    for key in ["failures", "errors", "skipped"]:
        try:
            declared = max((int(e.attrib.get(key, "0")) for e in root.iter() if e.tag in {"testsuite", "testsuites"}), default=0)
        except ValueError as exc:
            raise PipelineError(f"Invalid JUnit count: {path}") from exc
        result[key] = max(result[key], declared)
    return result

def validate_gate(report: dict, base: Path, requirements: dict, phase: str, fingerprint: str) -> None:
    if report.get("phase") != phase or report.get("source_fingerprint") != fingerprint:
        raise PipelineError("Gate report phase/source fingerprint mismatch")
    if report.get("production_authorized") is not False:
        raise PipelineError("Production is not authorized")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise PipelineError("Gate report missing checks array")
    seen = set()
    required = required_for(requirements, phase, "EXECUTABLE")
    for item in checks:
        rid = item.get("id")
        if rid in seen or rid not in required:
            raise PipelineError(f"Duplicate/unexpected executable check: {rid}")
        seen.add(rid)
        if item.get("status") != "PASS":
            raise PipelineError(f"Mandatory check not PASS: {rid}")
        safe_evidence(base, item.get("evidence", ""))
    if seen != required:
        raise PipelineError(f"Missing required checks: {sorted(required - seen)}")
    suites = report.get("suites")
    if not isinstance(suites, list):
        raise PipelineError("Missing suites array")
    total = 0
    reports = set()
    for suite in suites:
        path = safe_evidence(base, suite.get("report", ""))
        if path in reports:
            raise PipelineError(f"Duplicate JUnit report: {path}")
        reports.add(path)
        counts = junit_counts(path)
        for key in ["tests", "failures", "errors", "skipped"]:
            value = suite.get(key)
            if type(value) is not int or value < 0 or value != counts[key]:
                raise PipelineError(f"Suite {suite.get('name')} count mismatch: {key}")
        total += counts["tests"]
        if any(counts[key] for key in ["failures", "errors", "skipped"]):
            raise PipelineError(f"Failed/error/skipped mandatory suite: {suite.get('name')}")
    if phase != "M0" and total <= 0:
        raise PipelineError("No executed JUnit test cases")

def validate_agent(result: dict, phase: str, role: str, requirements: dict) -> None:
    if result.get("phase") != phase or result.get("role") != role:
        raise PipelineError("Agent phase/role mismatch")
    if result.get("status") not in {"COMPLETE", "CHANGES_REQUIRED", "BLOCKED"}:
        raise PipelineError("Unknown agent status")
    if result.get("production_authorized") is not False:
        raise PipelineError("Agent attempted to authorize production")
    for key in ["findings", "blockers", "evidence_paths", "verified_requirements"]:
        if not isinstance(result.get(key), list):
            raise PipelineError(f"Agent missing array: {key}")
    if result["status"] == "COMPLETE":
        if result["blockers"] or any(f.get("severity") in {"P0", "P1", "P2"} for f in result["findings"]):
            raise PipelineError("Agent claimed COMPLETE with blocking findings")
        if role == "REVIEWER":
            expected = required_for(requirements, phase, "REVIEW")
            if set(result["verified_requirements"]) != expected:
                raise PipelineError(f"Reviewer must verify review-only checks: {sorted(expected)}")

def execute(cmd: list[str], root: Path, log: Path, timeout: int,
            input_text: str | None = None, env: dict | None = None) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(cmd, cwd=root, env=env, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            process.communicate(input=input_text, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise PipelineError(f"Command interrupted/timed out; see {log}")
        return process.returncode

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--review-reasoning", default="xhigh")
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--max-agent-calls", type=int, default=64)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Actually invoke Codex and test scripts; default is dry-run")
    parser.add_argument("--ack-isolated-environment", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    kit = root / "ai-kit"
    for value in [args.max_rounds, args.max_agent_calls, args.timeout_seconds]:
        if value <= 0:
            parser.error("Budgets must be positive")
    expected = protected_files(root)
    requirements = load_json(kit / "requirements.json")
    if not args.execute:
        print(f"DRY RUN: {root}\nModel: {args.model}\nPhases: {' → '.join(PHASES)}")
        print(f"Up to {args.max_rounds} rounds per phase; up to {args.max_agent_calls} total agent calls.")
        print("Each round: fresh builder → direct test gate → fresh reviewer → repair if needed.")
        print("No Codex/test command executed. Add --execute --ack-isolated-environment to start.")
        return 0
    if not args.ack_isolated_environment:
        raise PipelineError("Generated tests run outside Codex sandbox. Use an isolated dev VM and explicitly acknowledge it.")
    if not shutil.which("codex") or not shutil.which("git") or not shutil.which("bash"):
        raise PipelineError("Missing codex/git/bash; install and authenticate Codex first")
    git = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True)
    if git.returncode or Path(git.stdout.strip()).resolve() != root:
        raise PipelineError("--repo must be the Git repository root")
    runroot = root / ".ai-run"
    runroot.mkdir(exist_ok=True)
    lock = (runroot / "runner.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise PipelineError("Another pipeline runner is active in this repository") from exc
    state_path = runroot / "state.json"
    if state_path.exists() and not args.resume:
        raise PipelineError("Existing run state found. Use --resume; do not run two builders against this repo")
    if args.resume and not state_path.exists():
        raise PipelineError("No runner state exists to resume")
    if args.resume:
        state = load_json(state_path)
    else:
        state = {"next_phase_index": 0, "agent_calls": 0, "phase_results": {}, "status": "RUNNING"}
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = runroot / run_id
    folder.mkdir()
    state["run_id"] = run_id
    state["model"] = args.model
    state["status"] = "RUNNING"
    atomic_json(state_path, state)
    subprocess.run(["codex", "--version"], cwd=root, stdout=(folder / "codex-version.txt").open("w"), check=True)
    def call_agent(phase: str, role: str, body: str, dest: Path) -> dict:
        if state["agent_calls"] >= args.max_agent_calls:
            raise PipelineError("BLOCKED_BUDGET: total agent call limit reached")
        state["agent_calls"] += 1
        atomic_json(state_path, state)
        dest.mkdir(parents=True, exist_ok=True)
        prompt = body + f"\n\nRunner context: phase={phase}; role={role}.\n"
        prompt += "Return the supplied JSON schema. Builder verified_requirements=[]; reviewer follows review-only AC requirements.\n"
        prompt += "The runner owns .ai-run; do not modify it. Never modify ai-kit or root AGENTS.md.\n"
        (dest / "input.md").write_text(prompt, encoding="utf-8")
        command = ["codex", "--ask-for-approval", "never", "--sandbox", "workspace-write", "--model", args.model,
                   "--config", f'model_reasoning_effort="{args.review_reasoning if role == "REVIEWER" else args.reasoning}"']
        if args.allow_network:
            command += ["--config", "sandbox_workspace_write.network_access=true"]
        command += ["exec", "--json", "--output-schema", str(kit / "schemas/agent-result.schema.json"),
                    "--output-last-message", str(dest / "result.json"), "-"]
        print(f"[{phase}] {role} call {state['agent_calls']} — log: {dest / 'transcript.log'}", flush=True)
        rc = execute(command, root, dest / "transcript.log", args.timeout_seconds, prompt)
        check_protected(root, expected)
        if rc:
            raise PipelineError(f"Codex exited {rc}; see {dest / 'transcript.log'} (auth/model/sandbox/quota may need attention)")
        result = load_json(dest / "result.json")
        validate_agent(result, phase, role, requirements)
        return result
    def gate(phase: str, label: str) -> tuple[bool, str, Path]:
        evidence = root / ".evidence" / run_id / label
        evidence.mkdir(parents=True, exist_ok=True)
        script = root / "scripts/verify-phase.sh"
        if not script.is_file():
            return False, "Missing scripts/verify-phase.sh", evidence
        fingerprint = source_fingerprint(root)
        env = dict(os.environ)
        env["ROUTE_SOURCE_FINGERPRINT"] = fingerprint
        # Do not forward API-key environment variables to generated test commands.
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)
        rc = execute(["bash", str(script), phase, str(evidence)], root, evidence / "verify.log", args.timeout_seconds, env=env)
        check_protected(root, expected)
        if source_fingerprint(root) != fingerprint:
            return False, "Gate changed source/config/docs; fix test outputs to use excluded evidence/build/cache directories", evidence
        try:
            if rc:
                raise PipelineError(f"Verification exit code {rc}")
            validate_gate(load_json(evidence / "summary.json"), evidence, requirements, phase, fingerprint)
        except PipelineError as exc:
            return False, str(exc), evidence
        return True, "PASS", evidence
    try:
        start = int(state["next_phase_index"])
        if not 0 <= start <= len(PHASES):
            raise PipelineError("Invalid resume state phase index")
        if args.resume and start > 0:
            # Revalidate the latest completed stage at the current source; never trust stale PASS.
            prev = min(start, len(PHASES)) - 1
            ok, reason, evidence = gate(PHASES[prev], "resume-preflight")
            if not ok:
                start = prev
                state["next_phase_index"] = start
                print(f"Resume preflight needs repair: {reason}; starting at {PHASES[start]}")
            elif start == len(PHASES):
                # A new final review is still required when resuming a completed run.
                start = len(PHASES) - 1
        for index in range(start, len(PHASES)):
            phase = PHASES[index]
            state["next_phase_index"] = index
            atomic_json(state_path, state)
            feedback = ""
            same_failure, last_signature = 0, None
            passed = False
            for round_no in range(1, args.max_rounds + 1):
                label = f"{phase}-round-{round_no}"
                dest = folder / label
                body = (kit / "prompts" / PROMPTS[index]).read_text(encoding="utf-8")
                if feedback:
                    body += "\n" + (kit / "prompts/10_FIX_FINDINGS.md").read_text() + "\nPrior feedback:\n" + feedback
                builder = call_agent(phase, "BUILDER", body, dest / "builder")
                if builder["status"] == "BLOCKED":
                    raise PipelineError("BLOCKED by builder: " + json.dumps(builder, ensure_ascii=False))
                ok, reason, evidence = gate(phase, label)
                if not ok:
                    feedback = f"Gate failed: {reason}. Read {evidence / 'verify.log'} and summary.json if present."
                    signature_payload = reason
                else:
                    before = source_fingerprint(root)
                    review_body = (kit / "prompts/09_INDEPENDENT_REVIEW.md").read_text()
                    review_body += f"\nPhase: {phase}. Gate evidence: {evidence}. Builder result: {dest / 'builder/result.json'}.\n"
                    review_body += "Inspect current source and all cumulative requirements. You may read logs/build outputs but make no source/document changes.\n"
                    reviewer = call_agent(phase, "REVIEWER", review_body, dest / "reviewer")
                    if source_fingerprint(root) != before:
                        raise PipelineError("Reviewer modified source/config/docs; no acceptance granted")
                    if reviewer["status"] == "BLOCKED":
                        raise PipelineError("BLOCKED by reviewer: " + json.dumps(reviewer, ensure_ascii=False))
                    if reviewer["status"] == "COMPLETE" and builder["status"] == "COMPLETE":
                        state["phase_results"][phase] = {"evidence": str(evidence.relative_to(root)),
                           "review": str((dest / "reviewer/result.json").relative_to(root)),
                           "source_fingerprint": before, "round": round_no}
                        state["next_phase_index"] = index + 1
                        atomic_json(state_path, state)
                        print(f"[{phase}] PASS: executable gate + fresh review", flush=True)
                        passed = True
                        break
                    feedback = json.dumps({"builder": builder, "reviewer": reviewer}, ensure_ascii=False, indent=2)
                    signature_payload = json.dumps({"builder_status": builder["status"], "reviewer_status": reviewer["status"], "findings": reviewer["findings"]}, ensure_ascii=False, sort_keys=True)
                signature = hashlib.sha256((source_fingerprint(root) + signature_payload).encode()).hexdigest()
                same_failure = same_failure + 1 if signature == last_signature else 1
                last_signature = signature
                if same_failure >= 3:
                    raise PipelineError(f"BLOCKED_STALLED: {phase} repeated identical failure without source progress")
            if not passed:
                raise PipelineError(f"BLOCKED_BUDGET: {phase} did not pass in {args.max_rounds} rounds. Latest feedback: {feedback}")
        state["status"] = "ENGINEERING_ACCEPTANCE_PASS"
        state["source_fingerprint"] = source_fingerprint(root)
        atomic_json(state_path, state)
        final = {"engineering_acceptance": "PASS", "external_acceptance": "NOT_RUN",
                 "production_deployment": "NOT_AUTHORIZED", "source_fingerprint": state["source_fingerprint"],
                 "agent_calls": state["agent_calls"], "model": args.model, "phase_results": state["phase_results"]}
        atomic_json(runroot / "FINAL_RESULT.json", final)
        print("ENGINEERING_ACCEPTANCE=PASS\nEXTERNAL_ACCEPTANCE=NOT_RUN\nPRODUCTION_DEPLOYMENT=NOT_AUTHORIZED")
        print(f"Result: {runroot / 'FINAL_RESULT.json'}")
        return 0
    except (PipelineError, OSError, ValueError, subprocess.SubprocessError) as exc:
        state["status"] = "BLOCKED"
        state["error"] = str(exc)
        state["source_fingerprint"] = source_fingerprint(root)
        atomic_json(state_path, state)
        atomic_json(runroot / "FINAL_RESULT.json", {"engineering_acceptance": "BLOCKED", "reason": str(exc),
                    "external_acceptance": "NOT_RUN", "production_deployment": "NOT_AUTHORIZED"})
        raise
    finally:
        lock.close()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PipelineError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(2)
