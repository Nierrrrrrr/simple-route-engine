"""Evidence-only process barrier for run-owned JVM crash acceptance; never a runtime lock."""
import json,os,pathlib,signal,time,uuid
from gate_common import ROOT

ISOLATION='REPEATABLE READ READ ONLY WITH CONSISTENT SNAPSHOT'

def identity(app):
 p=app['process'];assert p.poll() is None,'Crash target already exited'
 proc=pathlib.Path('/proc')/str(p.pid);status=(proc/'status').read_text().splitlines()
 result={'pid':p.pid,'parent_pid':int(next(x.split()[1] for x in status if x.startswith('PPid:'))),
         'cwd':str((proc/'cwd').resolve()),'executable':str((proc/'exe').resolve()),
         'command':(proc/'cmdline').read_bytes().decode().rstrip('\0').split('\0'),
         'start_ticks':int((proc/'stat').read_text().rsplit(')',1)[1].split()[19])}
 assert result['parent_pid']==os.getpid() and result['cwd']==str(ROOT),'Crash target is not our checkout child'
 assert result['executable']==str((ROOT/'.tools/java/bin/java').resolve()),'Crash target is not the fixture JDK'
 assert result['command']==[str(ROOT/'.tools/java/bin/java'),'-Duser.timezone=UTC','-jar','target/route-engine-0.1.0.jar'],'Unexpected fixture command'
 return result

def threads(app):
 return [{'tid':int(p.name),'state':next(x.split()[1] for x in (p/'status').read_text().splitlines() if x.startswith('State:'))}
         for p in sorted((pathlib.Path('/proc')/str(app['process'].pid)/'task').iterdir(),key=lambda x:int(x.name))]

def snapshot(f,id):
 assert str(uuid.UUID(id))==id
 query="""SET SESSION group_concat_max_len=1048576; SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;
SELECT JSON_OBJECT('execution',(SELECT CONCAT(state,':',permit_held) FROM executions WHERE id='{id}'),
'steps',COALESCE((SELECT GROUP_CONCAT(CONCAT(node_id,':',state,':',attempt_count,':',lease_generation,':',operation_generation) ORDER BY ordinal_number SEPARATOR '\\n') FROM step_runs WHERE execution_id='{id}'),''),
'attempts',COALESCE((SELECT GROUP_CONCAT(CONCAT(r.node_id,':',a.attempt_number,':',a.state,':',a.operation_id) ORDER BY r.ordinal_number,a.attempt_number SEPARATOR '\\n') FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id='{id}'),'')); COMMIT;""".format(id=id)
 args=f.sql_args(query);assert ' -N -e ' in args[5];args[5]=args[5].replace(' -N -e ',' -N --raw -e ')
 value=json.loads(f.command(args,'consistent-crash-snapshot'));assert set(value)=={'execution','steps','attempts'} and value['execution']
 return value

def db_activity(f,phase):
 # This administrator is only the disposable, already owner-checked container's fixture account.
 # No credentials are returned, logged or copied out of the container.
 query="SELECT JSON_OBJECT('database_clock',CAST(UTC_TIMESTAMP(6) AS CHAR),'active_transactions',(SELECT COUNT(*) FROM information_schema.INNODB_TRX),'lock_waits',(SELECT COUNT(*) FROM information_schema.INNODB_LOCK_WAITS),'active_commands',(SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE ID<>CONNECTION_ID() AND USER='route_test' AND COMMAND<>'Sleep'))"
 script='MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -u root "$MARIADB_DATABASE" -N --raw -e "$1"'
 value=json.loads(f.command(['docker','exec',f.name,'sh','-c',script,'_',query],'crash-database-activity'))
 return dict(value,phase=phase,monotonic_ns=time.monotonic_ns())

def validate_crash_boundary(record):
 b=record['boundary'];pids=record['killed_pids'];assert pids and len(pids)==len(set(pids))
 assert b['method']=='SIGSTOP_ALL_OWNED_WRITERS' and b['snapshot_isolation']==ISOLATION
 assert sorted(b['live_fixture_pids'])==sorted(pids) and len(b['live_fixture_pids'])==len(pids)
 processes=b['processes'];assert sorted(p['pid'] for p in processes)==sorted(pids) and len(processes)==len(pids)
 for p in processes:
  assert p['parent_pid']>0 and p['start_ticks']>0 and p['cwd']==str(ROOT)
  assert p['executable']==str((ROOT/'.tools/java/bin/java').resolve())
  assert p['command']==[str(ROOT/'.tools/java/bin/java'),'-Duser.timezone=UTC','-jar','target/route-engine-0.1.0.jar']
  ts=p['stopped_threads'];assert ts and len({t['tid'] for t in ts})==len(ts) and p['pid'] in {t['tid'] for t in ts}
  assert all(t['tid']>0 and t['state']=='T' for t in ts),'Every owned JVM thread must be stopped before snapshot'
 checks=b['db_checks'];assert [c['phase'] for c in checks]==['before_snapshot','after_snapshot']
 assert all(c['database_clock'] and c['active_transactions']==c['active_commands']==0 for c in checks),'Snapshot boundary has active DB work'
 events=b['events'];assert [e['name'] for e in events]==['stopped','snapshot_start','snapshot_end']+['kill']*len(pids)+['after_snapshot_start','after_snapshot_end']
 assert all(type(e['monotonic_ns']) is int and e['monotonic_ns']>0 for e in events)
 times=[e['monotonic_ns'] for e in events];assert times==sorted(set(times)),'Crash boundary event order invalid'
 assert times[0]<checks[0]['monotonic_ns']<times[1] and times[2]<checks[1]['monotonic_ns']<times[3]
 assert [e['pid'] for e in events if e['name']=='kill']==pids
 assert record['exit_codes']==[-9]*len(pids)
 assert record['before']==record['after_kill'],'Crash must not mutate persistent state'

def crash(f,apps,id,window):
 assert apps and all(any(a is known for known in f.apps) for a in apps),'Crash target not owned by this fixture'
 live=[a for a in f.apps if a['process'].poll() is None]
 assert {a['process'].pid for a in apps}=={a['process'].pid for a in live} and len(apps)==len(live),'All live fixture writers must participate'
 owner=json.loads(f.command(['docker','inspect','--format','{{json .Config.Labels}}',f.name],'crash-database-owner'))
 assert owner.get('route-engine.run-id')==f.run and owner.get('route-engine.purpose')=='foundation-test'
 attempts=[];events=[];failure=None;pids=[a['process'].pid for a in apps]
 try:
  for attempt in range(10):
   identities=[identity(a) for a in apps]
   for a,expected in zip(apps,identities):
    assert identity(a)==expected;a['process'].send_signal(signal.SIGSTOP)
   f.wait(lambda:all(all(t['state']=='T' for t in threads(a)) for a in apps),'all owned JVM threads stopped',5)
   stopped=time.monotonic_ns()
   for a,p in zip(apps,identities):
    assert identity(a)==p;p['stopped_threads']=threads(a)
   activity=db_activity(f,'before_snapshot');attempts.append({'attempt':attempt+1,'processes':identities,'db_check':activity})
   if activity['active_transactions']==activity['active_commands']==0:break
   # A client may have stopped inside a short transaction. Resume it to finish;
   # never kill, snapshot or pretend that uncommitted work is quiescent.
   attempts[-1]['resumes']=[];attempts[-1]['drain_observations']=[]
   for a,p in zip(apps,identities):
    current=identity(a);assert all(current[k]==p[k] for k in current)
    a['process'].send_signal(signal.SIGCONT);attempts[-1]['resumes'].append({'pid':a['process'].pid,'monotonic_ns':time.monotonic_ns()})
   def drained():
    value=db_activity(f,'retry_drain');attempts[-1]['drain_observations'].append(value)
    return value['active_transactions']==value['active_commands']==0
   f.wait(drained,'in-flight fixture DB work drains',10)
  else:raise AssertionError('Could not establish a stopped and DB-idle crash boundary')
  events.append({'name':'stopped','monotonic_ns':stopped});events.append({'name':'snapshot_start','monotonic_ns':time.monotonic_ns()})
  before=f.snapshot(id);events.append({'name':'snapshot_end','monotonic_ns':time.monotonic_ns()})
  final_activity=db_activity(f,'after_snapshot');assert final_activity['active_transactions']==final_activity['active_commands']==0,'DB work appeared after stopped snapshot'
  for a,p in zip(apps,identities):
   current=identity(a);assert all(current[k]==p[k] for k in current) and all(t['state']=='T' for t in threads(a))
   events.append({'name':'kill','pid':a['process'].pid,'monotonic_ns':time.monotonic_ns()});f.kill(a);assert a['process'].returncode==-9
  events.append({'name':'after_snapshot_start','monotonic_ns':time.monotonic_ns()});after=f.snapshot(id);events.append({'name':'after_snapshot_end','monotonic_ns':time.monotonic_ns()})
  record={'window':window,'execution':id,'killed_pids':pids,'exit_codes':[a['process'].returncode for a in apps],'before':before,'after_kill':after,
          'boundary':{'method':'SIGSTOP_ALL_OWNED_WRITERS','live_fixture_pids':pids,'processes':identities,'snapshot_isolation':ISOLATION,'db_checks':[activity,final_activity],'events':events,'quiescence_attempts':attempts}}
  f.crashes.append(record);validate_crash_boundary(record);return record
 except Exception as error:
  failure=str(error);raise
 finally:
  (f.base/('crash-boundary-'+id+'.json')).write_text(json.dumps({'window':window,'attempts':attempts,'events':events,'failure':failure},indent=2)+'\n')
