-- The existing published-version triggers protect this column with the full immutable row.
-- Historical versions stay NULL: do not infer their external semantics from today's catalog.
ALTER TABLE route_versions ADD COLUMN adapter_bindings JSON NULL;
