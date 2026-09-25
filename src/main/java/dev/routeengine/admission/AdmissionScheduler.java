package dev.routeengine.admission;

import org.slf4j.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.*;

@Configuration @EnableScheduling
@ConditionalOnProperty(name="route.scheduler.enabled",havingValue="true",matchIfMissing=true)
public class AdmissionScheduler {
 private static final Logger log=LoggerFactory.getLogger(AdmissionScheduler.class);
 private final AdmissionService admission;
 public AdmissionScheduler(AdmissionService admission){this.admission=admission;}
 @Scheduled(fixedDelayString="${route.scheduler.delay-ms:250}")
 public void wake(){
  try{for(int i=0;i<32;i++)if(admission.tick()==null)break;}
  catch(RuntimeException e){log.warn("Admission wake failed; persisted requests remain for next database scan ({})",e.getClass().getSimpleName());}
 }
}