package dev.routeengine.api;

import com.fasterxml.jackson.databind.JsonNode;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.recovery.*;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import org.springframework.dao.DataAccessException;
import org.springframework.http.*;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.annotation.*;
import java.time.Instant;

@RestController
@RequestMapping(produces=MediaType.APPLICATION_JSON_VALUE)
public class RecoveryController {
 private final AdmissionService admission;private final OperatorService operator;
 public RecoveryController(AdmissionService admission,OperatorService operator){this.admission=admission;this.operator=operator;}
 private String actor(HttpServletRequest r){return (String)r.getAttribute("actor");}
 private String rid(HttpServletRequest r){return (String)r.getAttribute("requestId");}
 @GetMapping("/executions/{id}/incidents") JsonNode incidents(@PathVariable String id){return operator.incidents(id);}
 @PostMapping("/executions/{id}/recoveries") ResponseEntity<?> recover(@PathVariable String id,@RequestHeader(value="Idempotency-Key",required=false) String key,@Valid @RequestBody RecoveryPolicy.Request body,HttpServletRequest r,HttpServletResponse response){
  if(key==null||!key.matches("[A-Za-z0-9._:-]{1,128}"))throw ApiProblem.invalid();
  String identity=AdmissionService.identity(actor(r),AdmissionService.recoveryScope(id),key);response.setHeader("X-Admission-Request-ID",identity);
  try{var result=admission.recover(id,actor(r),key,body,rid(r));return ResponseEntity.status(result.status()).body(result.body());}
  catch(DataAccessException|TransactionException unavailable){return ResponseEntity.status(503).body(new AdmissionController.Unavailable("DATABASE_UNAVAILABLE","Outcome unavailable; query or retry the same identity",rid(r),Instant.now(),identity));}
 }
 @PostMapping("/executions/{id}/cancel") ResponseEntity<JsonNode> cancel(@PathVariable String id,@RequestHeader(value="Idempotency-Key",required=false) String key,@Valid @RequestBody OperatorService.Cancel body,HttpServletRequest r){
  return ResponseEntity.accepted().body(operator.cancel(id,actor(r),key,body,rid(r)));
 }
 @PostMapping("/executions/{id}/incidents/{incidentId}/resolve") JsonNode resolve(@PathVariable String id,@PathVariable String incidentId,@RequestHeader(value="Idempotency-Key",required=false) String key,@Valid @RequestBody OperatorService.Resolve body,HttpServletRequest r){
  return operator.resolve(id,incidentId,actor(r),key,body,rid(r));
 }
}
