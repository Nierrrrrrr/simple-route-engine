package dev.routeengine.operations;
import io.micrometer.core.instrument.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
/** Durable observations, not reservations or a cache for admission. Failures return NaN. */
@Component public class EngineMetrics {
 private final JdbcTemplate db;
 public EngineMetrics(JdbcTemplate db,MeterRegistry meters){
  this.db=db;
  gauge(meters,"route.queue.depth","SELECT COUNT(*) FROM admission_requests WHERE decision='QUEUED'");
  gauge(meters,"route.permits.total","SELECT COUNT(*) FROM executions WHERE permit_held=TRUE");
  gauge(meters,"route.permits.noncritical","SELECT COUNT(*) FROM executions WHERE permit_held=TRUE AND priority<>'CRITICAL'");
  gauge(meters,"route.admission.rejected","SELECT COUNT(*) FROM admission_requests WHERE decision='REJECTED'");
  gauge(meters,"route.retry.wait","SELECT COUNT(*) FROM step_runs WHERE state='RETRY_WAIT'");
  gauge(meters,"route.in.doubt","SELECT COUNT(*) FROM step_runs WHERE state='IN_DOUBT'");
  gauge(meters,"route.stalled","SELECT COUNT(*) FROM executions WHERE permit_held=TRUE AND updated_at < UTC_TIMESTAMP() - INTERVAL 5 MINUTE");
  gauge(meters,"route.lease.expired","SELECT COUNT(*) FROM step_runs WHERE lease_until < UTC_TIMESTAMP(6) AND state IN ('RUNNING','WAITING_EXTERNAL','IN_DOUBT')");
  gauge(meters,"route.reconcile.events","SELECT COUNT(*) FROM execution_events WHERE event_type='OPERATION_RECONCILING'");
  gauge(meters,"route.scheduler.lag.seconds","SELECT COALESCE(GREATEST(0,TIMESTAMPDIFF(SECOND,MIN(next_action_at),UTC_TIMESTAMP())),0) FROM executions WHERE permit_held=TRUE");
 }
 private void gauge(MeterRegistry meters,String name,String sql){Gauge.builder(name,()->read(sql)).description("MariaDB durable observation").register(meters);}
 private double read(String sql){try{return db.queryForObject(sql,Double.class);}catch(RuntimeException unavailable){return Double.NaN;}}
}
