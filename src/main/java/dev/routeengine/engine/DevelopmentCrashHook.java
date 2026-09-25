package dev.routeengine.engine;
import java.nio.file.*;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Deterministic crash-window probe. Never registered by default or used as durable business state. */
@Component
@Profile("engine-development")
public class DevelopmentCrashHook implements EngineHook {
 private final Path base;private final String node;
 public DevelopmentCrashHook(@Value("${route.engine.fixture-directory}") String directory,@Value("${route.engine.pause-after-node:}") String node){
  this.base=Path.of(directory).toAbsolutePath().normalize();this.node=node;
 }
 private Path path(String execution,String suffix){return base.resolve("pause-"+execution+suffix);}
 public boolean allowClaim(String execution){return node.isEmpty()||!Files.exists(path(execution,".armed"))||Files.exists(path(execution,".release"));}
 public void beforeCompletion(EngineService.Work w){
  if(!w.request().node().path("id").asText().equals(node))return;
  if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Fault hook within transaction");
  try{Files.createDirectories(base);Files.writeString(path(w.executionId(),".armed"),w.stepId());}catch(IOException e){throw new IllegalStateException("Fault hook unavailable");}
 }
 public void afterCompletion(EngineService.Work w){
  if(!w.request().node().path("id").asText().equals(node))return;
  if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Fault hook within transaction");
  try{
   Files.writeString(path(w.executionId(),".reached"),w.stepId());
   while(!Files.exists(path(w.executionId(),".release"))){Thread.sleep(50);}
  }catch(InterruptedException e){Thread.currentThread().interrupt();}catch(IOException e){throw new IllegalStateException("Fault hook unavailable");}
 }
}