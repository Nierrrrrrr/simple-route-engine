"""M5 public API, independent JVM races and real HTTP recovery crash windows."""
import json,uuid,traceback,time,concurrent.futures,subprocess,select,os,xml.etree.ElementTree as ET
import crash_boundary
from adapter_fixture import AdapterFixture
from engine_gate import leaf

def process_acceptance(base):
 base.mkdir(parents=True,exist_ok=False);f=AdapterFixture(base);suite=ET.Element('testsuite',name='RecoveryProcesses');problem=None;proof={'races':[],'crashes':[]}
 def case(name,fn):
  c=ET.SubElement(suite,'testcase',classname='RecoveryProcesses',name=name)
  try:fn()
  except Exception:ET.SubElement(c,'failure').text=traceback.format_exc();raise
 def incidents(app,id):return f.api(app,'GET','/executions/'+id+'/incidents',expected=200)[1]['incidents']
 def manual(app,ref='flaky'):
  id=f.execute(app,[leaf('bad',ref)])
  f.wait(lambda:f.status(id)=='MANUAL_WAIT:0','known failure safe stop');return id
 def request(app,id,action='RETRY',mode='NOW_OR_REJECT'):
  i=incidents(app,id);assert len(i)==1
  return {'incidentId':i[0]['incidentId'],'stepId':i[0]['stepId'],'action':action,'admissionMode':mode,'reason':'isolated fixture verified decision'}
 def recover(app,id,body,key=None,expected=202):
  return f.api(app,'POST','/executions/'+id+'/recoveries',body,key or str(uuid.uuid4()),expected)[1]
 def counts(id):
  ops=f.sql("SELECT operation_id FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id='"+id+"'").splitlines()
  return {op:{'effects':f.remote.effects.get(op,0),'submits':sum(x['operation']==op for x in f.remote.submits)} for op in ops}
 try:
  f.start();f.setup_catalog();app=f.start_adapter('recovery-api')
  def discovery():
   id=manual(app,'failure');i=incidents(app,id)
   assert len(i)==1 and i[0]['stepId'] and i[0]['operationId'] and i[0]['actions']==['CANCEL','RETRY','SKIP']
   body=request(app,id,'SKIP');before=f.snapshot(id)
   for extra in [{'priority':'CRITICAL'},{'actor':'forged'},{'unexpected':True}]:
    f.api(app,'POST','/executions/'+id+'/recoveries',dict(body,**extra),str(uuid.uuid4()),422)
    assert before==f.snapshot(id)
   proof['discovery']={'execution':id,'incident':i[0],'unknownFieldsRejected':3,'unchanged':True}
  case('AC043_AC049_operatorDiscoveryStrictPriorityAndActorFields',discovery)
  def races():
   other=f.start_adapter('recovery-race-peer',engine='false')
   id=manual(app);second=manual(app);body=request(app,id,mode='QUEUE');key='same-key'
   with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    responses=list(pool.map(lambda n:f.api([app,other][n%2],'POST','/executions/'+id+'/recoveries',body,key),range(20)))
   assert all(status==202 for status,_ in responses) and len({json.dumps(x,sort_keys=True) for _,x in responses})==1
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE execution_id='"+id+"' AND recovery_payload IS NOT NULL")=='1'
   base_body=request(app,second,mode='QUEUE')
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    actions=list(pool.map(lambda pair:f.api(pair[0],'POST','/executions/'+second+'/recoveries',dict(base_body,action=pair[1]),str(uuid.uuid4())),[(app,'RETRY'),(other,'CANCEL')]))
   assert sorted(s for s,_ in actions)==[202,409]
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE execution_id='"+second+"' AND decision='QUEUED'")=='1'
   proof['races'].append({'pids':[app['process'].pid,other['process'].pid],'sameKeyRequests':20,'sameKeyDecisions':1,'differentActionStatuses':sorted(s for s,_ in actions)})
   for execution in [id,second]:f.api(app,'POST','/executions/'+execution+'/cancel',{'reason':'withdraw test queue'},str(uuid.uuid4()),202)
   f.kill(other)
  case('AC044_twoIndependentJvmsSameKeyReplayAndDifferentActionRace',races)
  def running_cancel():
   id=f.execute(app,[leaf('active','async'),leaf('never','sync')]);f.wait(lambda:f.status(id).endswith(':1') and f.operation(id,'active'),'real active operation')
   f.wait(lambda:f.step(id,'active')=='WAITING_EXTERNAL','actual HTTP accepted')
   op=f.operation(id,'active');generation=f.sql("SELECT permit_generation FROM executions WHERE id='"+id+"'")
   body={'reason':'stop settled external fixture'}
   f.api(app,'POST','/executions/'+id+'/cancel',body,'cancel',202)
   f.wait(lambda:f.status(id)=='CANCELLED:0','external cancellation convergence')
   assert f.remote.operations[op]['status']=='STOPPED' and f.operation(id,'active')==op and f.step(id,'never')==''
   assert f.sql("SELECT permit_generation FROM executions WHERE id='"+id+"'")==generation
   f.api(app,'POST','/executions/'+id+'/cancel',body,'cancel',202)
   proof['runningCancel']={'generation':int(generation),'externalStatus':f.remote.operations[op]['status'],'counts':counts(id)}
  case('AC048_runningCancellationUsesExistingPermitAndActualStopObservation',running_cancel)
  def resolve():
   id=f.execute(app,[leaf('unknown','unsafe'),leaf('after','sync')]);f.wait(lambda:f.status(id)=='RECONCILING:1','unsafe operation incident');i=incidents(app,id)[0]
   url='/executions/'+id+'/incidents/'+i['incidentId']+'/resolve'
   body={'stepId':i['stepId'],'operationId':i['operationId'],'outcome':'SUCCEEDED','reason':'remote record checked','evidence':'isolated HTTP fixture exact operation terminal success','output':{'value':'confirmed'}}
   for changed in [dict(body,operationId=str(uuid.uuid4())),dict(body,evidence='')]:
    f.api(app,'POST',url,changed,str(uuid.uuid4()),409 if changed['operationId']!=body['operationId'] else 422)
   first=f.api(app,'POST',url,body,'resolve',200)[1];f.wait(lambda:f.status(id)=='SUCCEEDED:0','resolved route advances')
   assert first==f.api(app,'POST',url,body,'resolve',200)[1]
   assert counts(id)[i['operationId']]=={'effects':1,'submits':1}
   assert f.sql("SELECT COUNT(*) FROM execution_events WHERE execution_id='"+id+"' AND event_type='OPERATOR_RESOLVED' AND actor='local-admin' AND reason LIKE '%evidence:%'")=='1'
   proof['resolve']={'existingOperation':i['operationId'],'counts':counts(id),'state':f.status(id),'audited':True}
  case('AC049_evidenceResolvesExactRealUnknownOperationWithoutResubmission',resolve)
  for window in ['after-enqueue','after-admission','during-external-work','after-result-release']:
   def crash_window(window=window):
    nonlocal app
    id=manual(app);old_operation=f.operation(id,'bad');f.kill(app)
    a=f.start_adapter(window,engine='false' if window in ['after-enqueue','after-admission'] else 'true',
      pause='bad' if window=='during-external-work' else '',after='bad' if window=='after-result-release' else '')
    body=request(a,id,mode='QUEUE' if window=='after-enqueue' else 'NOW_OR_REJECT');decision=recover(a,id,body,'crash-key')
    if window=='after-enqueue':assert f.status(id)=='RECOVERY_QUEUED:0'
    elif window=='after-admission':assert f.status(id)=='RECOVERING:1'
    elif window=='during-external-work':
     f.wait(lambda:(f.external/('io-'+id+'.reached')).exists(),'recovery real HTTP result before DB')
     assert f.status(id)=='RECOVERING:1' and f.step(id,'bad')=='RUNNING'
    else:
     f.wait(lambda:(f.external/('pause-'+id+'.reached')).exists(),'result and permit release committed')
     assert f.status(id)=='SUCCEEDED:0'
    before_counts=counts(id);record=f.crash([a],id,'recovery-'+window)
    app=f.start_adapter(window+'-restart',scheduler='true')
    f.wait(lambda:f.status(id)=='SUCCEEDED:0','recovery restart converges '+window)
    assert recover(app,id,body,'crash-key')==decision
    assert f.sql("SELECT permit_generation FROM executions WHERE id='"+id+"'")=='2'
    assert f.step(id,'bad','attempt_count')=='2'
    final_counts=counts(id);assert len(final_counts)==2 and all(v=={'effects':1,'submits':1} for v in final_counts.values())
    time.sleep(.3);assert final_counts==counts(id)
    new_operation=f.operation(id,'bad');assert new_operation!=old_operation
    record.update(restarted_pid=app['process'].pid,after_restart=f.snapshot(id),old_operation=old_operation,new_operation=new_operation,before_counts=before_counts,counts=final_counts,permit_generation=2)
    proof['crashes'].append(record)
   case('AC042_AC043_AC050_realHttpRecoveryCrash_'+window.replace('-','_'),crash_window)
  def transaction_boundary():
   nonlocal app
   id=manual(app);old_operation=f.operation(id,'bad');f.kill(app)
   app=f.start_adapter('boundary-drain-before',pause='bad');body=request(app,id);recover(app,id,body,'boundary-drain')
   f.wait(lambda:(f.external/('io-'+id+'.reached')).exists(),'real result held for transaction boundary')
   script='MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u "$MARIADB_USER" "$MARIADB_DATABASE" -N --unbuffered'
   args=['docker','exec','-i',f.name,'sh','-c',script]
   (base/'boundary-lock.command.json').write_text(json.dumps(args)+'\n')
   holder=subprocess.Popen(args,cwd=f.base,env=f.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
   held_output=b'';released=False;observations=[];original=crash_boundary.db_activity
   try:
    holder.stdin.write(b"START TRANSACTION; SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE; SELECT 'BOUNDARY_LOCK_HELD';\n");holder.stdin.flush()
    deadline=time.monotonic()+10
    while b'BOUNDARY_LOCK_HELD' not in held_output:
     assert time.monotonic()<deadline and holder.poll() is None,'Fixture lock holder failed'
     if select.select([holder.stdout],[],[],.2)[0]:held_output+=os.read(holder.stdout.fileno(),4096)
    (base/'boundary-lock.log').write_bytes(held_output)
    f.wait(lambda:original(f,'waiting_for_real_jvm_transaction')['lock_waits']>0,'actual JVM transaction waits on owned pool row',10)
    def release_after_observed_stop(fixture,phase):
     nonlocal released
     value=original(fixture,phase)
     if phase=='before_snapshot' and not released:
      assert value['active_transactions']>0 and value['lock_waits']>0
      assert all(t['state']=='T' for t in crash_boundary.threads(app))
      observations.append(value);holder.stdin.write(b'COMMIT;\n');holder.stdin.close();holder.wait(timeout=10);assert holder.returncode==0
      (base/'boundary-lock.exit').write_text(str(holder.returncode)+'\n');released=True
     return value
    crash_boundary.db_activity=release_after_observed_stop
    record=f.crash([app],id,'recovery-stopped-during-db-transaction')
   finally:
    crash_boundary.db_activity=original
    if holder.poll() is None:
     if holder.stdin and not holder.stdin.closed:holder.stdin.write(b'ROLLBACK;\n');holder.stdin.close()
     holder.wait(timeout=10)
    if holder.stdout:holder.stdout.close()
   assert released and observations
   attempts=record['boundary']['quiescence_attempts'];assert len(attempts)>=2 and attempts[0]['resumes'] and attempts[0]['db_check']['active_transactions']>0
   assert attempts[-1]['db_check']['active_transactions']==0
   app=f.start_adapter('boundary-drain-restart');f.wait(lambda:f.status(id)=='SUCCEEDED:0','recovery after coordinated DB boundary')
   record.update(restarted_pid=app['process'].pid,after_restart=f.snapshot(id),permit_generation=int(f.sql("SELECT permit_generation FROM executions WHERE id='"+id+"'")),counts=counts(id),old_operation=old_operation,new_operation=f.operation(id,'bad'),blocked_transaction_observations=observations)
   assert record['permit_generation']==2 and len(record['counts'])==2 and all(v=={'effects':1,'submits':1} for v in record['counts'].values())
   proof['boundaryDrain']=record
  case('AC050_stoppedJvmWithRealInFlightTransactionResumesAndDrainsBeforeSnapshot',transaction_boundary)
 except Exception as error:problem=error;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  (base/'recovery-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
  try:f.cleanup()
  except Exception as error:problem=problem or error;(base/'cleanup-failure.log').write_text(traceback.format_exc())
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-RecoveryProcesses.xml',encoding='utf-8',xml_declaration=True)
 if problem:raise problem
if __name__=='__main__':
 import sys,pathlib
 process_acceptance(pathlib.Path(sys.argv[1]).resolve())
