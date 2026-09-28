package dev.routeengine.engine;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.*;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import org.slf4j.*;

@Component
@EnableScheduling
@ConditionalOnProperty(name="route.engine.enabled",havingValue="true",matchIfMissing=true)
public class EngineScheduler {
 private static final Logger log=LoggerFactory.getLogger(EngineScheduler.class);
 private final EngineService engine;private final ThreadPoolExecutor workers;
 public EngineScheduler(EngineService engine,@Value("${route.engine.workers:4}") int count,@Value("${route.engine.queue-size:16}") int queue){
  if(count<1||count>32||queue<1||queue>256)throw new IllegalArgumentException("Invalid worker bounds");
  this.engine=engine;workers=new ThreadPoolExecutor(count,count,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(queue),new ThreadPoolExecutor.AbortPolicy());
 }
 @Scheduled(fixedDelayString="${route.engine.scan-ms:100}")
 public void scan(){
  try{for(String id:engine.candidates(64)){
   try{workers.execute(()->{try{engine.tick(id);}catch(Exception ordinary){log.warn("Execution worker interrupted; durable state retained");}});}
   catch(RejectedExecutionException full){break;}
  }}catch(Exception database){log.warn("Engine scan unavailable; durable work retained");}
 }
 public int maximumWorkers(){return workers.getMaximumPoolSize();}
 public int queueCapacity(){return workers.getQueue().remainingCapacity()+workers.getQueue().size();}
 @PreDestroy public void stop(){workers.getQueue().clear();workers.shutdown();try{if(!workers.awaitTermination(5,TimeUnit.SECONDS))workers.shutdownNow();}catch(InterruptedException e){Thread.currentThread().interrupt();workers.shutdownNow();}}
}