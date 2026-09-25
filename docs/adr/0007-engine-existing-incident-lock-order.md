# ADR0007: acquire existing incidents before step work

Fixed architecture section6 requires pool -> execution -> incident/admission -> step. Round3's
independent reviewer used an actual MariaDB trace to show that terminal complete updated an existing
attempt before acquiring its existing incident. Global pool serialization did not waive this protocol.

EngineService.execution now acquires scheduler_pool, the execution, then all existing incidents for that
execution ordered by id with SELECT FOR UPDATE. Every claim, result transaction and pre-I/O ownership
check uses this helper before any step or attempt mutation. It includes resolved and legacy history,
because subsequent structural or budget logic must not acquire an older incident after step work.
The acquisition itself changes no incident identity/status. Terminal result SQL still requires exact
attempt, operation, direction, operation generation and permit generation, plus the existing lease/CAS.

Path audit:
- complete terminal: existing incident locks are already held before the attempt update and exact
  incident resolution; result, next pending nodes, audit and safe permit release remain one transaction.
- complete repeated UNKNOWN: the existing row is acquired first even when incident() finds it already
  present and inserts nothing. No blind resubmit or new business attempt is introduced.
- claim elapsed budget -> fail: existing history is acquired before structural/step updates and before
  adding KNOWN_FAILURE for the prior known terminal attempt.
- fresh UNKNOWN/failure: a new UUID incident has no pre-existing row to acquire. The parent execution is
  already held; step/attempt FK validation occurs in the step tier after existing incidents were locked.
  Own uncommitted insert and unique-key/FK checks do not mean updating an older incident out of order.
- nested AdmissionService.stop reuses the already held pool/execution rows; it does not first acquire a
  new higher-order row after step work. Initial tree expansion and lease reclaim use the same entrance.

Three actual MariaDB tests deliberately hold an existing incident in a separate test-only transaction.
A worker runs the real mutation; PROCESSLIST identifies its blocked incident SQL. An independent third
connection must acquire NOWAIT locks on both the step and attempt before the incident is released.
This distinguishes actual lock acquisition from statement-text inspection. Original code failed all3:
terminal had already locked the attempt, while repeated UNKNOWN and budget failure did not wait at all.
Waits remain bounded by2 seconds and existing DB lock timeout; no sleep/timeout adjustment masks order.
These tests intentionally hold a lock to measure contention; production external I/O remains outside Tx.

Original reviewer ad hoc failures and approval rejection remain unchanged in round3 evidence. This ADR
implements the fixed order; it does not claim a previously observed deadlock or amend the architecture.
