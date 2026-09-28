package dev.routeengine.engine;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
/** Process lifecycle only; all cross-process admission/fencing stays in MariaDB. */
@Component
public class ClaimLifecycle {
 private final AtomicBoolean stopping=new AtomicBoolean();
 public boolean stopping(){return stopping.get();}
 @EventListener @Order(Ordered.HIGHEST_PRECEDENCE)
 public void stop(ContextClosedEvent event){stopping.set(true);}
}
