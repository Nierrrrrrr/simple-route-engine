"""A real claim waits for the pool row across SIGTERM; no sleeps stand in for the barrier."""
import json,os,select,subprocess,time,traceback,xml.etree.ElementTree as ET
from hardening_processes import HardeningFixture
from crash_boundary import db_activity

def acceptance(base,jar=None):
 base.mkdir(parents=True,exist_ok=False);f=HardeningFixture(base);holder=None;problem=None
 suite=ET.Element('testsuite',name='ShutdownClaim');case=ET.SubElement(suite,'testcase',classname='ShutdownClaim',name='AC053_claimBlockedOnDatabaseMustRecheckShutdown')
 try:
  f.start();f.setup_catalog();seed=f.launch('seed',jar)
  id=f.execute(seed,[{'id':'work','type':'REST','endpointRef':'sync'}]);f.kill(seed)
  assert f.status(id)=='ADMITTED:1' and not f.operation(id,'work')
  args=['docker','exec','-i',f.name,'sh','-c','MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u "$MARIADB_USER" "$MARIADB_DATABASE" -N --unbuffered']
  (base/'lock.command.json').write_text(json.dumps(args))
  holder=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);output=b''
  holder.stdin.write(b"START TRANSACTION; SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE; SELECT 'LOCK_HELD';\n");holder.stdin.flush()
  deadline=time.monotonic()+10
  while b'LOCK_HELD' not in output:
   assert holder.poll() is None and time.monotonic()<deadline
   if select.select([holder.stdout],[],[],.1)[0]:output+=os.read(holder.stdout.fileno(),4096)
  (base/'lock.log').write_bytes(output)
  app=f.launch('blocked-claim',jar,{'ROUTE_ENGINE_ENABLED':'true'})
  blocked=f.wait(lambda:(v if (v:=db_activity(f,'shutdown-claim')).get('lock_waits',0)>0 else None),'real blocked transaction')
  app['process'].terminate()
  f.wait(lambda:'Commencing graceful shutdown' in (base/'jvm-blocked-claim.log').read_text(),'context close actually started',10)
  holder.stdin.write(b'COMMIT;\n');holder.stdin.close();assert holder.wait(timeout=10)==0
  exitcode=app['process'].wait(timeout=25);app['stream'].close();assert exitcode==143
  attempts=int(f.sql("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id='"+id+"'"))
  effects=len(f.remote.submits)
  observed={'pid':app['process'].pid,'blocked':blocked,'exit':exitcode,'attemptsAfterShutdown':attempts,'submitsAfterShutdown':effects,'stateAfterShutdown':f.status(id)}
  (base/'shutdown-proof.json').write_text(json.dumps(observed,indent=2)+'\n')
  assert attempts==0 and effects==0,'A claim blocked on the pool row must not commit after context shutdown'
  new=f.launch('restart',jar,{'ROUTE_ENGINE_ENABLED':'true'});f.wait(lambda:f.status(id)=='SUCCEEDED:0','safe restart claim')
  assert len(f.remote.submits)==1 and sum(f.remote.effects.values())==1
  observed.update(restartPid=new['process'].pid,finalState=f.status(id),restartSubmits=1,restartEffects=1)
  (base/'shutdown-proof.json').write_text(json.dumps(observed,indent=2)+'\n')
 except Exception as e:problem=e;ET.SubElement(case,'failure').text=traceback.format_exc();(base/'failure.log').write_text(traceback.format_exc())
 finally:
  if holder and holder.poll() is None:
   if not holder.stdin.closed:holder.stdin.write(b'ROLLBACK;\n');holder.stdin.close()
   holder.wait(timeout=10)
  if holder and holder.stdout:holder.stdout.close()
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-ShutdownClaim.xml',encoding='utf-8',xml_declaration=True);f.cleanup()
 if problem:raise problem
if __name__=='__main__':
 import sys,pathlib
 acceptance(pathlib.Path(sys.argv[1]).resolve(),pathlib.Path(sys.argv[2]).resolve() if len(sys.argv)>2 else None)
