package dev.routeengine.registry;

import com.fasterxml.jackson.databind.*;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.audit.AuditLog;
import java.sql.*;
import java.time.*;
import java.util.*;
import org.springframework.dao.*;
import org.springframework.jdbc.core.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RouteRegistry {
 @org.springframework.beans.factory.annotation.Autowired private PersistenceGuard guard;
 public record Route(String routeId,String name,boolean enabled,Instant deletedAt,int maxVersion,Integer latestPublishedVersion,long stateVersion,Instant createdAt,Instant updatedAt){}
 public record Version(String routeId,int version,String status,JsonNode definition,String definitionHash,String dslVersion,String engineSemanticsVersion,String adapterContractVersion,long stateVersion,Instant createdAt,Instant publishedAt){}
 private final JdbcTemplate db;private final TransactionTemplate tx;private final AuditLog audit;private final DefinitionRules rules;private final ObjectMapper json;private final dev.routeengine.adapters.AdapterBindings bindings;
 public RouteRegistry(JdbcTemplate db,TransactionTemplate tx,AuditLog audit,DefinitionRules rules,ObjectMapper json,dev.routeengine.adapters.AdapterBindings bindings){this.db=db;this.tx=tx;this.audit=audit;this.rules=rules;this.json=json;this.bindings=bindings;}
 private Instant time(ResultSet r,String name)throws SQLException{var t=r.getObject(name,LocalDateTime.class);return t==null?null:t.toInstant(ZoneOffset.UTC);}
 private Route route(ResultSet r,int row)throws SQLException{return new Route(r.getString("route_id"),r.getString("name"),r.getBoolean("enabled"),time(r,"deleted_at"),r.getInt("max_version"),r.getObject("latest_published_version",Integer.class),r.getLong("state_version"),time(r,"created_at"),time(r,"updated_at"));}
 private Version version(ResultSet r,int row)throws SQLException{
  try{return new Version(r.getString("route_id"),r.getInt("version"),r.getString("status"),json.readTree(r.getString("definition_json")),r.getString("definition_hash"),r.getString("dsl_version"),r.getString("engine_semantics_version"),r.getString("adapter_contract_version"),r.getLong("state_version"),time(r,"created_at"),time(r,"published_at"));}
  catch(com.fasterxml.jackson.core.JsonProcessingException e){throw new SQLException("Stored definition is invalid",e);}
 }
 public List<Route> list(){return db.query("SELECT * FROM routes ORDER BY route_id",this::route);}
 public Route get(String id){try{return db.queryForObject("SELECT * FROM routes WHERE route_id=?",this::route,id);}catch(EmptyResultDataAccessException e){throw ApiProblem.missing();}}
 private Route lock(String id){try{return db.queryForObject("SELECT * FROM routes WHERE route_id=? FOR UPDATE",this::route,id);}catch(EmptyResultDataAccessException e){throw ApiProblem.missing();}}
 public List<Version> versions(String id){get(id);var result=db.query("SELECT * FROM route_versions WHERE route_id=? ORDER BY version",this::version,id);for(var v:result)protectRead(v);return result;}
 public Version getVersion(String id,int v){try{var result=db.queryForObject("SELECT * FROM route_versions WHERE route_id=? AND version=?",this::version,id,v);protectRead(result);return result;}catch(EmptyResultDataAccessException e){throw ApiProblem.missing();}}
 private void protectRead(Version v){if(!org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())guard.prepare(v.definition(),v.status().equals("PUBLISHED")?guard.bound(v.routeId(),v.version()):null,json.createObjectNode());}
 private void mutable(Route r){if(r.deletedAt()!=null)throw ApiProblem.conflict();}
 private void changed(int count){if(count!=1)throw ApiProblem.conflict();}
 public Route create(String id,String name,String actor,String requestId){
  try{return tx.execute(s->{db.update("INSERT INTO routes(route_id,name) VALUES(?,?)",id,name);audit.append(null,id,null,"ROUTE_CREATED",actor,"create route",requestId);return get(id);});}
  catch(DuplicateKeyException e){throw ApiProblem.conflict();}
 }
 private record EnvelopeContext(String route,Integer version,String snapshot,List<PersistenceGuard.Prepared> checks){}
 private List<Version> envelopeVersions(String id,Integer version){return version==null?db.query("SELECT * FROM route_versions WHERE route_id=? ORDER BY version",this::version,id):db.query("SELECT * FROM route_versions WHERE route_id=? AND version=?",this::version,id,version);}
 private EnvelopeContext prepareEnvelope(String id,Integer version,JsonNode payload){
  var versions=envelopeVersions(id,version);var checks=new ArrayList<PersistenceGuard.Prepared>();
  for(var v:versions)checks.add(guard.prepare(v.definition(),v.status().equals("PUBLISHED")?guard.bound(id,v.version()):null,payload));
  return new EnvelopeContext(id,version,rules.hash(json.valueToTree(versions)),List.copyOf(checks));
 }
 /** Route lock excludes draft, binding, publication and withdrawal changes during these pure rechecks. */
 private void recheckEnvelope(EnvelopeContext context,JsonNode payload){
  var versions=envelopeVersions(context.route(),context.version());if(!context.snapshot().equals(rules.hash(json.valueToTree(versions))))throw ApiProblem.conflict();
  for(int i=0;i<versions.size();i++){var v=versions.get(i);guard.recheck(context.checks().get(i),v.definition(),v.status().equals("PUBLISHED")?guard.bound(v.routeId(),v.version()):null,payload);}
 }
 public Route update(String id,String name,boolean enabled,long state,String actor,String requestId){
  var envelope=guard.envelope(null,name,requestId);var context=prepareEnvelope(id,null,envelope);
  return tx.execute(s->{var r=lock(id);mutable(r);recheckEnvelope(context,envelope);changed(db.update("UPDATE routes SET name=?,enabled=?,state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE route_id=? AND state_version=?",name,enabled,id,state));audit.append(null,id,null,"ROUTE_UPDATED",actor,"update metadata and enablement",requestId);return get(id);});
 }
 public Route delete(String id,long state,String actor,String requestId){
  var envelope=guard.envelope(null,requestId);var context=prepareEnvelope(id,null,envelope);
  return tx.execute(s->{var r=lock(id);mutable(r);recheckEnvelope(context,envelope);changed(db.update("UPDATE routes SET enabled=FALSE,deleted_at=UTC_TIMESTAMP(6),updated_at=UTC_TIMESTAMP(6),state_version=state_version+1 WHERE route_id=? AND state_version=?",id,state));audit.append(null,id,null,"ROUTE_DELETED",actor,"soft delete route",requestId);return get(id);});
 }
 public Version draft(String id,JsonNode definition,String actor,String requestId){
  var envelope=guard.envelope(null,requestId);var prepared=guard.prepare(definition,null,envelope);
  return tx.execute(s->{var route=lock(id);mutable(route);int v=Math.addExact(route.maxVersion(),1);rules.validate(id,v,definition);guard.recheck(prepared,definition,null,envelope);
   db.update("INSERT INTO route_versions(route_id,version,status,definition_json,definition_hash,dsl_version,engine_semantics_version,adapter_contract_version) VALUES(?,?,'DRAFT',?,?, '1','1','1')",id,v,rules.canonical(definition),rules.hash(definition));
   changed(db.update("UPDATE routes SET max_version=?,state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE route_id=? AND state_version=?",v,id,route.stateVersion()));
   audit.append(null,id,v,"DRAFT_CREATED",actor,"create version draft",requestId);return getVersion(id,v);
  });
 }
 public Version edit(String id,int v,JsonNode definition,long state,String actor,String requestId){
  var envelope=guard.envelope(null,requestId);var prepared=guard.prepare(definition,null,envelope);var context=prepareEnvelope(id,v,envelope);
  return tx.execute(s->{mutable(lock(id));recheckEnvelope(context,envelope);var old=getVersion(id,v);if(!old.status().equals("DRAFT"))throw ApiProblem.conflict();rules.validate(id,v,definition);guard.recheck(prepared,definition,null,envelope);
   changed(db.update("UPDATE route_versions SET definition_json=?,definition_hash=?,state_version=state_version+1 WHERE route_id=? AND version=? AND status='DRAFT' AND state_version=?",rules.canonical(definition),rules.hash(definition),id,v,state));
   audit.append(null,id,v,"DRAFT_UPDATED",actor,"update draft",requestId);return getVersion(id,v);
  });
 }
 public Version publish(String id,int v,long state,String actor,String requestId){
  var envelope=guard.envelope(null,requestId);var selected=getVersion(id,v);var frozenBinding=bindings.publish(selected.definition());var prepared=guard.prepare(selected.definition(),frozenBinding,envelope);
  return tx.execute(s->{var route=lock(id);mutable(route);var old=getVersion(id,v);if(!old.status().equals("DRAFT"))throw ApiProblem.conflict();rules.validate(id,v,old.definition());
   guard.recheck(prepared,old.definition(),bindings.publish(old.definition()),envelope);
   String frozen=rules.canonical(frozenBinding);
   changed(db.update("UPDATE route_versions SET adapter_bindings=?,status='PUBLISHED',published_at=UTC_TIMESTAMP(6),state_version=state_version+1 WHERE route_id=? AND version=? AND status='DRAFT' AND state_version=?",frozen,id,v,state));
   changed(db.update("UPDATE routes SET latest_published_version=GREATEST(COALESCE(latest_published_version,0),?),state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE route_id=? AND state_version=?",v,id,route.stateVersion()));
   audit.append(null,id,v,"VERSION_PUBLISHED",actor,"publish immutable version",requestId);return getVersion(id,v);
  });
 }
 public Map<String,Object> withdraw(String id,int v,long state,String actor,String requestId){
  var envelope=guard.envelope(null,requestId);var context=prepareEnvelope(id,v,envelope);
  return tx.execute(s->{mutable(lock(id));recheckEnvelope(context,envelope);var old=getVersion(id,v);if(!old.status().equals("DRAFT"))throw ApiProblem.conflict();
   changed(db.update("DELETE FROM route_versions WHERE route_id=? AND version=? AND status='DRAFT' AND state_version=?",id,v,state));
   audit.append(null,id,v,"DRAFT_WITHDRAWN",actor,"withdraw unpublished version without reusing number",requestId);return Map.of("routeId",id,"version",v,"withdrawn",true);
  });
 }
 /** Pool must already be held by the caller; route lock protects new-admission eligibility. */
 public Version lockForNewExecution(String id,Integer requestedVersion){lock(id);return resolveForNewExecution(id,requestedVersion);}
 /** Foundation selector. Admission must call it inside its own pool-first transaction (M2). */
 public Version resolveForNewExecution(String id,Integer requestedVersion){
  var route=get(id);if(route.deletedAt()!=null||!route.enabled())throw new ApiProblem(422,"ROUTE_DISABLED","Route does not accept new executions");
  Integer v=requestedVersion==null?route.latestPublishedVersion():requestedVersion;if(v==null)throw ApiProblem.invalid();
  var result=getVersion(id,v);if(!result.status().equals("PUBLISHED"))throw ApiProblem.invalid();
  rules.validate(id,v,result.definition());return result;
 }
}
