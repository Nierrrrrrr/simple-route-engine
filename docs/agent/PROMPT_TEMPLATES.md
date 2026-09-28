# Agent task templates

## Add an existing-node route

Read AGENTS.md, fixed contracts, docs/agent/ADD_ROUTE.md and DSL_REFERENCE. Create a labelled DEMO JSON based on examples/delivery using existing node types. Do not modify Java or published versions. Validate/draft/publish/execute against an explicitly supplied isolated fixture API and preserve actual request/status/execution evidence. Never use production credentials. Do not claim completion until terminal SUCCEEDED and unaffected examples are checked.

## Change a route version

Read CHANGE_ROUTE.md and RouteRegistry. Create version2, retain a queued version1 execution and prove it still uses version1 definitionHash/adapter binding. Test publish immutability and disabled-route new-admission rejection; old recovery must retain its priority and definition. Record raw commands and new version evidence.

## Add an adapter

Read ADD_ADAPTER.md, OperationAdapter, AdapterBindings and DefinitionRules. Specify submit/observe/cancel, identity, unknown outcomes, retry and output/credential safety before implementation. Use a controlled deployment-owned reference. Add genuine isolated protocol tests and crash-after-side-effect/restart evidence. Update API/DSL/extension docs and run cumulative M6. No new runtime service or production access.

## Fix a race

Read CHANGE_ENGINE.md, TRANSACTIONS and the exact failing raw proof. Reproduce a failure with independently running JVMs and MariaDB; preserve pool -> execution -> incident/admission -> step/attempt ordering and permit/lease/operation generations. Add a regression before the smallest repair. Do not weaken assertions or replace actual I/O with mocks. Freeze documents and code for a fresh reviewer; never approve your own fix.
