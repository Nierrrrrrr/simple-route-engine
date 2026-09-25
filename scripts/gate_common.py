"""Import only the fixed validator library. Never invoke its orchestration main."""
import importlib.util, pathlib, sys
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('route_fixed_validator', ROOT/'ai-kit/tools/run_pipeline.py')
fixed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixed)

def evidence_path(root, value):
    base = pathlib.Path(value).resolve()
    if not base.is_relative_to(root/'.evidence') or base == root/'.evidence':
        raise fixed.PipelineError('Evidence must be a child of repository .evidence')
    return base
