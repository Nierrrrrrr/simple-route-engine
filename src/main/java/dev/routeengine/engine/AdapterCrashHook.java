package dev.routeengine.engine;
import java.nio.file.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
/** Local test-only barrier after real adapter I/O and before saving its result. */
@Component @Profile("engine-development")
public class AdapterCrashHook implements EngineHook {
 private final Path base;private final String node;
 public AdapterCrashHook(@Value("${route.engine.fixture-directory}") String path,@Value("${route.engine.pause-before-result-node:}") String node){base=Path.of(path);this.node=node;}
 public void beforeResult(EngineService.Work work){
  if(node.isBlank()||!node.equals(work.request().node().path("id").asText()))return;
  if(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Crash barrier inside transaction");
  try{
   Files.createDirectories(base);Files.writeString(base.resolve("io-"+work.executionId()+".reached"),work.request().operationId());
   while(!Files.exists(base.resolve("io-"+work.executionId()+".release")))Thread.sleep(50);
  }catch(InterruptedException interrupted){Thread.currentThread().interrupt();}
  catch(java.io.IOException failure){throw new IllegalStateException("Crash barrier unavailable");}
 }
}
