package dev.routeengine.api;

import com.fasterxml.jackson.databind.JsonNode;
import dev.routeengine.admission.AdmissionService;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import org.springframework.dao.DataAccessException;
import org.springframework.http.*;
import org.springframework.transaction.TransactionException;
import org.springframework.web.bind.annotation.*;
import java.time.Instant;

@RestController
@RequestMapping(produces=MediaType.APPLICATION_JSON_VALUE)
public class AdmissionController {
 private final AdmissionService service;
 public AdmissionController(AdmissionService service){this.service=service;}
 private String actor(HttpServletRequest r){return (String)r.getAttribute("actor");}
 private String rid(HttpServletRequest r){return (String)r.getAttribute("requestId");}
 public record Unavailable(String code,String message,String requestId,Instant timestamp,String admissionRequestId){}
 @PostMapping("/executions") ResponseEntity<?> submit(@RequestHeader(value="Idempotency-Key",required=false) String key,@Valid @RequestBody AdmissionService.Request body,HttpServletRequest request,HttpServletResponse response){
  if(key==null||!key.matches("[A-Za-z0-9._:-]{1,128}"))throw ApiProblem.invalid();
  String id=AdmissionService.identity(actor(request),key);response.setHeader("X-Admission-Request-ID",id);
  try{var result=service.submit(actor(request),key,body,rid(request));return ResponseEntity.status(result.status()).body(result.body());}
  catch(DataAccessException|TransactionException unavailable){return ResponseEntity.status(503).body(new Unavailable("DATABASE_UNAVAILABLE","Outcome unavailable; query or retry the same identity",rid(request),Instant.now(),id));}
 }
 @GetMapping("/executions/{id}") JsonNode execution(@PathVariable String id,HttpServletRequest r){return service.execution(actor(r),id,java.util.Set.of("admin","operator").contains(r.getAttribute("role")));}
 @GetMapping("/admission-requests/{id}") JsonNode lookup(@PathVariable String id,HttpServletRequest r){return service.lookup(actor(r),id);}
 @GetMapping("/admission-requests") JsonNode lookupKey(@RequestParam String key,HttpServletRequest r){if(!key.matches("[A-Za-z0-9._:-]{1,128}"))throw ApiProblem.invalid();return service.lookup(actor(r),AdmissionService.identity(actor(r),key));}
 @GetMapping("/capacity") JsonNode capacity(){return service.capacity();}
 @PutMapping("/capacity/config") JsonNode configure(@Valid @RequestBody AdmissionService.Config body,HttpServletRequest r){return service.configure(body,actor(r),rid(r));}
}