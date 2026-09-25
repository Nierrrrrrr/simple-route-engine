# State machines (normative M0 design)

## Execution and permit

| State | Permit | Legal next states and guard |
|---|---|---|
| QUEUED | no | ADMITTED on atomic scheduler admission; CANCELLED on queue withdrawal |
| ADMITTED | yes | RUNNING after durable initialization; CANCELING on stop intent |
| RUNNING | yes | WAITING_EXTERNAL, RETRY_WAIT, PAUSING, RECONCILING, CANCELING, SUCCEEDED when settled |
| WAITING_EXTERNAL | yes | RUNNING on observed success; RETRY_WAIT on known retryable failure; PAUSING or RECONCILING |
| RETRY_WAIT | yes | RUNNING when persisted next_action_at is due; PAUSING/CANCELING |
| PAUSING | yes | MANUAL_WAIT only after ALL_SETTLED including failure notification; RECONCILING if unknown |
| RECONCILING | yes | RUNNING on known success; PAUSING/CANCELING after known failure/stopped; no unsafe new submit |
| CANCELING | yes | CANCELLED only after every launched operation terminal/stopped; RECONCILING if uncertain |
| MANUAL_WAIT | no | RECOVERY_QUEUED for QUEUE; RECOVERING/ROLLING_BACK for admitted NOW; reject remains unchanged |
| RECOVERY_QUEUED | no | RECOVERING/ROLLING_BACK after incident revalidation, original priority, new queue timestamp |
| RECOVERING | yes, new generation | RUNNING after retry/skip; CANCELING for manual CANCEL; PAUSING if failed |
| ROLLING_BACK | yes, new generation | MANUAL_WAIT when compensation succeeds and settles; RETRY_WAIT/PAUSING on bounded failure |
| SUCCEEDED/FAILED/CANCELLED | no | terminal, no recovery; FAILED is not a substitute for human decision |

Entering MANUAL_WAIT/terminal and releasing the matching permit generation is one DB transaction.
Lease expiry, HTTP timeout, DELETE Job accepted, or a missing previously-submitted Job never prove safe release.
`IN_DOUBT` is an operation/incident condition: execution is RECONCILING and retains its permit.
No force-release or force-retry default exists. Operator resolve records evidence for an existing operation only.

## Step, attempt and recovery

Step: PENDING → READY → LEASED → RUNNING → WAITING_EXTERNAL/SUCCEEDED/RETRY_WAIT/FAILED.
FAILED known failure → incident after started sibling branches settle; SUCCEEDED branch remains untouched on retry.
SKIPPED requires typed replacement output if downstream nodes depend on output. A parallel join uses ALL_SETTLED,
stores each branch output separately, then merges once. CONDITION/when decisions persist before dispatch.

Attempt: INTENT_COMMITTED → SUBMITTED → OBSERVING → SUCCEEDED/FAILED/STOPPED; ambiguous submit/observe → IN_DOUBT.
Persist FORWARD or ROLLBACK direction. Transport retries retain operation_generation and external identity;
a new business attempt increments operation_generation only when the prior result is known and adapter permits it.
lease_generation fences worker writes independently; permit_generation fences release independently.

Recovery: REQUESTED → QUEUED/ADMITTED → EXECUTING → COMPLETED/FAILED; rejected NOW creates only an idempotent
decision, no pending recovery and no incident/step mutation. One active recovery per incident is enforced in DB.
RETRY targets only the failed step/direction. ROLLBACK requires that step's explicit compensation and legal incident,
cannot target a step consumed by later successful work, and returns to MANUAL_WAIT without automatic continuation.

Manual CANCEL uses recovery QUEUE/NOW and obtains a new permit before stopping and releasing.
Running cancel retains its existing permit, stops new dispatch, waits for terminal external work, never compensates implicitly.
Queued withdrawal cancels the unadmitted request without creating recovery work.

## M3 executable subset

Control nodes persist PENDING -> RUNNING -> SUCCEEDED/FAILED/STOPPED/SKIPPED. Activities use
PENDING -> RUNNING -> SUCCEEDED/FAILED/WAITING_EXTERNAL/RETRY_WAIT/IN_DOUBT. Only known retryable
failure creates a new attempt/operation. Observation advances lease_generation while retaining identity.
Elapsed retry budget fails without submit. Known failure sets PAUSING while started work/notifications
converge. Unknown sets RECONCILING and holds permit; it does not become failure or permit resubmission.
A known terminal observation resolves its unknown incident in the result transaction. Container output
maps child IDs only after children settle. Completed siblings remain intact. All-settled root success
enters SUCCEEDED; failed/stopped root enters MANUAL_WAIT, atomically releasing permit_generation.
M5 implements the normative operator recovery/cancel/rollback transitions above.

V4 incident lifecycle is per immutable attempt/operation/direction, independent of lease renewal.
UNKNOWN creates OPEN for the current attempt. Known terminal observation resolves only that incident
with result/audit/next work in the same transaction. A new business retry gets a new operation and can
create a new OPEN incident; prior RESOLVED history remains. Legacy V3 rows are explicitly unbound and
are never guessed into a current operation or automatically resolved. M5 rejects legacy-unbound recovery/resolve.

## M4 executable running cancellation

The internal running-permit EngineService.requestCancel persists cancel_requested and CANCELING.
New dispatch stops, including isolated PENDING or RETRY_WAIT failure notifications; these become STOPPED
without creating another attempt. Existing operations continue through adapter.cancel/observe. UNKNOWN
takes precedence as RECONCILING and keeps the permit. All settled rows plus terminal attempts allow
CANCELLED and matching-generation permit release atomically. No implicit compensation occurs.
Kubernetes stop intent records the exact resource UID before delete; both resource and operation Pods
must disappear before STOPPED. This currently covers synchronous local Pod work only.
M5 exposes these transitions through authenticated RecoveryController and OperatorService.

## M5 recovery execution
Manual -> RECOVERY_QUEUED without permit; admission revalidates current incident -> RECOVERING/ROLLING_BACK with permit_generation+1. Rejected NOW leaves execution, incident and steps unchanged. Original decision/audit is still durable.
RETRY consumes the old incident, preserves operation history and resets only retry_base/first_attempt_at for a new finite window. Only the chosen failed leaf runs while other failed branches remain stopped; structural ancestors reopen without changing branch_choice. Successful sibling rows/output do not change.
SKIP records validated replacement output and reopens ancestors. Resolved downstream references accept this explicit SKIPPED output. Compensation is a separate ROLLBACK step_run linked by recovery_origin_id. Success creates a new COMPENSATED incident and returns MANUAL_WAIT; its only legal next action is CANCEL. Failure creates a fresh rollback KNOWN_FAILURE; human RETRY continues rollback with a new bounded window. Old incidents stay resolved.
Manual CANCEL acquires/releases a new generation. Running cancel holds the current permit until all attempts stop. Withdrawal of queued recovery removes the pending request and returns MANUAL_WAIT without a new generation. Exact-operation resolve can confirm SUCCEEDED/FAILED/STOPPED while fencing old observers; it never submits new I/O.


M5 dispatch/cancel ordering: a fresh operation is dispatched at the claim transaction's durable INTENT_COMMITTED commit under pool -> execution locks. A later cancel commit prevents any new fresh claim, including pending parallel siblings and subsequent sequence work. An operation claimed before cancellation may still submit afterward with its saved identity. It retains the original permit and is subsequently cancelled/observed; a DELETE202 or WAITING result never proves termination. Only terminal evidence plus convergence of every started operation releases the permit. No cross-system atomic promise of zero HTTP requests after cancel returns is made. RecoveryCancellationIT controls claim -> public cancel -> execute against actual HTTP and an independently configured MariaDB; the M5 gate requires its ordered POST/DELETE/GET/DELETE/GET proof. DB fencing still does not revoke an already-sent HTTP request.
