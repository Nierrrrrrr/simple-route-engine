package dev.routeengine.engine;
import java.time.Clock;
import org.springframework.context.annotation.*;
@Configuration
public class EngineConfiguration {
 @Bean Clock engineDomainClock(){return Clock.systemUTC();}
}