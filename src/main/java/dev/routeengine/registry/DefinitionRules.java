package dev.routeengine.registry;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.api.ApiProblem;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import org.springframework.stereotype.Component;

/** Finite tree DSL. References can only read typed, previously settled values in their branch. */
@Component
public class DefinitionRules {
 private final ObjectMapper json;
 public DefinitionRules(ObjectMapper json){this.json=json;}
 private void require(boolean condition){if(!condition)throw ApiProblem.invalid();}
 private void fields(JsonNode n,Set<String> allowed){require(n.isObject());n.fieldNames().forEachRemaining(k->require(allowed.contains(k)));}
 public void validate(String routeId,int version,JsonNode d){
  require(d!=null);fields(d,Set.of("routeId","version","dslVersion","engineSemanticsVersion","adapterContractVersion","inputSchema","root"));
  require(d.path("routeId").isTextual()&&d.path("routeId").asText().equals(routeId)&&d.path("version").isIntegralNumber()&&d.path("version").canConvertToInt()&&d.path("version").asInt()==version);
  for(String key:List.of("dslVersion","engineSemanticsVersion","adapterContractVersion"))require(d.path(key).isTextual()&&d.path(key).asText().equals("1"));
  if(d.has("inputSchema")){schema(d.get("inputSchema"),0);require(d.get("inputSchema").isEmpty()||d.get("inputSchema").path("type").asText().equals("object"));}
  require(d.path("root").path("type").asText().equals("SEQUENCE"));
  node(d.path("root"),new HashSet<>(),new LinkedHashMap<>(),d.path("inputSchema"),0,0,false);
  require(canonical(d).getBytes(StandardCharsets.UTF_8).length<=262144);
 }
 private JsonNode node(JsonNode n,Set<String> ids,Map<String,JsonNode> prior,JsonNode input,int depth,int parallel,boolean compensation){
  require(depth<=20&&n.isObject()&&n.path("id").isTextual()&&n.path("id").asText().matches("[A-Za-z][A-Za-z0-9_-]{0,127}")&&ids.add(n.path("id").asText())&&ids.size()<=100);
  require(n.path("type").isTextual());String type=n.path("type").asText();JsonNode result=json.createObjectNode();
  var allowed=new HashSet<>(Set.of("id","type","when"));
  if(n.has("when"))comparison(n.get("when"),prior,input);
  switch(type){
   case "SEQUENCE" -> {
    require(!compensation);allowed.add("children");require(n.path("children").isArray());
    var visible=new LinkedHashMap<>(prior);ObjectNode props=json.createObjectNode();
    for(var child:n.get("children")){var shape=node(child,ids,visible,input,depth+1,parallel,false);props.set(child.path("id").asText(),shape);visible.put(child.path("id").asText(),shape);}
    result=objectSchema(props);
   }
   case "PARALLEL" -> {
    require(!compensation&&parallel==0);allowed.addAll(Set.of("branches","join"));
    require(n.path("join").asText().equals("ALL_SETTLED")&&n.path("branches").isArray()&&n.get("branches").size()>=1&&n.get("branches").size()<=10);
    ObjectNode props=json.createObjectNode();
    for(var child:n.get("branches"))props.set(child.path("id").asText(),node(child,ids,new LinkedHashMap<>(prior),input,depth+1,parallel+1,false));
    result=objectSchema(props);
   }
   case "CONDITION" -> {
    require(!compensation);allowed.addAll(Set.of("condition","then","else"));comparison(n.path("condition"),prior,input);
    node(n.path("then"),ids,new LinkedHashMap<>(prior),input,depth+1,parallel,false);
    node(n.path("else"),ids,new LinkedHashMap<>(prior),input,depth+1,parallel,false);
    // Choice-specific values are not guaranteed across both arms; no untyped downstream reference.
   }
   case "REST","KUBERNETES","ANSIBLE" -> {
    String ref=switch(type){case "REST"->"endpointRef";case "KUBERNETES"->"resourceRef";default->"playbookRef";};
    allowed.addAll(Set.of(ref,"input","outputSchema","artifactDigest","credentialRef","retry"));
    require(n.path(ref).isTextual()&&n.path(ref).asText().matches("[A-Za-z][A-Za-z0-9_.-]{0,127}"));
    if(n.has("input")){require(n.get("input").isObject());bindings(n.get("input"),prior,input,0);}
    if(n.has("outputSchema")){schema(n.get("outputSchema"),0);result=n.get("outputSchema");}
    if(n.has("credentialRef"))require(n.get("credentialRef").isTextual()&&n.get("credentialRef").asText().matches("[A-Za-z][A-Za-z0-9_.-]{0,127}"));
    if(n.has("artifactDigest"))require(n.get("artifactDigest").isTextual()&&n.get("artifactDigest").asText().matches("sha256:[a-f0-9]{64}"));
    if(n.has("retry"))retry(n.get("retry"));
    if(!compensation){
     allowed.addAll(Set.of("rollback","onFailure"));
     if(n.has("rollback"))node(n.get("rollback"),ids,new LinkedHashMap<>(prior),input,depth+1,parallel,true);
     if(n.has("onFailure")){var f=n.get("onFailure");fields(f,Set.of("endpointRef","maxAttempts"));require(f.path("endpointRef").isTextual()&&f.path("endpointRef").asText().matches("[A-Za-z][A-Za-z0-9_.-]{0,127}"));integer(f,"maxAttempts",1,10);}
    }
   }
   default -> throw ApiProblem.invalid();
  }
  fields(n,allowed);
  return n.has("when")?json.createObjectNode():result;
 }
 private JsonNode objectSchema(ObjectNode properties){ObjectNode s=json.createObjectNode().put("type","object");s.set("properties",properties);var req=s.putArray("required");properties.fieldNames().forEachRemaining(req::add);return s;}
 public void retry(JsonNode r){fields(r,Set.of("maxAttempts","maxElapsedSeconds","backoffSeconds","maxBackoffSeconds"));integer(r,"maxAttempts",1,100);integer(r,"maxElapsedSeconds",1,604800);integer(r,"backoffSeconds",0,86400);if(r.has("maxBackoffSeconds")){integer(r,"maxBackoffSeconds",0,86400);require(r.get("maxBackoffSeconds").asLong()>=r.get("backoffSeconds").asLong());}}
 private void integer(JsonNode n,String k,int min,int max){require(n.path(k).isIntegralNumber()&&n.path(k).canConvertToInt()&&n.path(k).asInt()>=min&&n.path(k).asInt()<=max);}
 private void comparison(JsonNode c,Map<String,JsonNode> prior,JsonNode input){
  fields(c,Set.of("field","operator","value"));require(c.path("field").isTextual()&&c.path("operator").isTextual());
  String type=reference(c.get("field").asText(),prior,input,!c.path("operator").asText().equals("EXISTS")).path("type").asText(),op=c.get("operator").asText();
  require(Set.of("EQ","NE","LT","LE","GT","GE","EXISTS").contains(op));
  require(Set.of("string","boolean","number","integer").contains(type));
  if(op.equals("EXISTS"))require(!c.has("value"));
  else {require(c.has("value"));value(type,c.get("value"));if(Set.of("LT","LE","GT","GE").contains(op))require(type.equals("number")||type.equals("integer"));}
 }
 private JsonNode reference(String ref,Map<String,JsonNode> prior,JsonNode input,boolean required){
  require(ref.matches("(input|steps\\.[A-Za-z][A-Za-z0-9_-]{0,127})(\\.[A-Za-z][A-Za-z0-9_-]{0,127})+"));
  String[] p=ref.split("\\.");JsonNode schema;int at;
  if(p[0].equals("input")){schema=input;at=1;}else{require(prior.containsKey(p[1]));schema=prior.get(p[1]);at=2;}
  for(;at<p.length;at++){require(schema.path("type").asText().equals("object"));boolean mandatory=false;for(var key:schema.path("required"))if(key.asText().equals(p[at]))mandatory=true;require(!required||mandatory);schema=schema.path("properties").path(p[at]);require(!schema.isMissingNode());}
  require(schema.has("type"));return schema;
 }
 private void bindings(JsonNode n,Map<String,JsonNode> prior,JsonNode input,int depth){
  require(depth<=20);
  if(n.isObject()&&n.has("$ref")){fields(n,Set.of("$ref"));require(n.get("$ref").isTextual());reference(n.get("$ref").asText(),prior,input,true);return;}
  if(n.isContainerNode()){var it=n.fields();while(it.hasNext()){var e=it.next();require(!Set.of("password","secret","token","authorization","privatekey").contains(e.getKey().toLowerCase(Locale.ROOT)));bindings(e.getValue(),prior,input,depth+1);}if(n.isArray())for(var v:n)bindings(v,prior,input,depth+1);}
 }
 private void schema(JsonNode s,int depth){
  require(depth<=20);fields(s,Set.of("type","properties","required","additionalProperties"));if(s.isEmpty())return;
  String type=s.path("type").asText();require(Set.of("object","string","boolean","number","integer").contains(type));
  if(type.equals("object")){
   if(s.has("properties")){require(s.get("properties").isObject());s.get("properties").fields().forEachRemaining(e->{require(e.getKey().matches("[A-Za-z][A-Za-z0-9_-]{0,127}"));schema(e.getValue(),depth+1);});}
   if(s.has("required")){require(s.get("required").isArray());Set<String> seen=new HashSet<>();for(var k:s.get("required"))require(k.isTextual()&&s.path("properties").has(k.asText())&&seen.add(k.asText()));}
   if(s.has("additionalProperties"))require(s.get("additionalProperties").isBoolean());
  }else require(s.size()==1);
 }
 private void value(String type,JsonNode v){require(switch(type){case "string"->v.isTextual();case "boolean"->v.isBoolean();case "number"->v.isNumber();case "integer"->v.isIntegralNumber();case "object"->v.isObject();default->false;});}
 public void validateValue(JsonNode schema,JsonNode v){
  if(schema.isMissingNode()||schema.isEmpty())return;
  String type=schema.path("type").asText();value(type,v);
  if(type.equals("object")){
   for(var k:schema.path("required"))require(v.has(k.asText()));
   v.fields().forEachRemaining(e->{if(schema.path("properties").has(e.getKey()))validateValue(schema.get("properties").get(e.getKey()),e.getValue());else require(!schema.has("additionalProperties")||schema.get("additionalProperties").asBoolean());});
  }
 }
 public String canonical(JsonNode value){return sort(value).toString();}
 private JsonNode sort(JsonNode n){if(n.isObject()){ObjectNode result=json.createObjectNode();var keys=new TreeSet<String>();n.fieldNames().forEachRemaining(keys::add);keys.forEach(k->result.set(k,sort(n.get(k))));return result;}if(n.isArray()){ArrayNode result=json.createArrayNode();n.forEach(v->result.add(sort(v)));return result;}return n;}
 public String hash(JsonNode value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical(value).getBytes(StandardCharsets.UTF_8)));}catch(NoSuchAlgorithmException e){throw new IllegalStateException(e);}}
}