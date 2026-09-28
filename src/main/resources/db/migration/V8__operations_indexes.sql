-- Additive only: preserves all published definitions, attempts and pending decisions.
CREATE INDEX ix_execution_operations ON executions(permit_held, updated_at);
CREATE INDEX ix_step_reconcile ON step_runs(state, lease_until);
