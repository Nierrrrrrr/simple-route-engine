package dev.routeengine.adapters;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.engine.OperationAdapter;
import org.springframework.stereotype.Component;
import java.util.*;
/** Pure version-level semantics. No file, credential, database or network I/O. */
@Component
public class AdapterBindings {
 private final ObjectMapper json;private final List<OperationAdapter> adapters;
 public AdapterBindings(ObjectMapper json,List<OperationAdapter> adapters){this.json=json;this.adapters=List.copyOf(adapters);}
 private String key(JsonNode n){String type=n.path("type").asText();return type+":"+n.path(type.equals("REST")?"endpointRef":type.equals("ANSIBLE")?"playbookRef":"resourceRef").asText();}
 private JsonNode current(JsonNode n){
  var found=adapters.stream().filter(a->a.supports(n)).toList();if(found.size()!=1)throw ApiProblem.invalid();
  try{JsonNode binding=found.getFirst().binding(n);if(!binding.isObject()||binding.isEmpty())throw ApiProblem.invalid();return binding;}
  catch(IllegalArgumentException e){throw ApiProblem.invalid();}
 }
 public JsonNode publish(JsonNode definition){
  var result=json.createObjectNode().put("contract",1);var refs=result.putObject("references");visit(definition.path("root"),refs);return result;
 }
 private void visit(JsonNode node,ObjectNode refs){
  String type=node.path("type").asText();
  if(Set.of("REST","KUBERNETES","ANSIBLE").contains(type)){
   JsonNode binding=current(node),old=refs.get(key(node));if(old!=null&&!old.equals(binding))throw ApiProblem.invalid();refs.set(key(node),binding.deepCopy());
  }
  for(String field:List.of("children","branches"))for(JsonNode child:node.path(field))visit(child,refs);
  for(String field:List.of("then","else","rollback"))if(node.has(field))visit(node.get(field),refs);
  if(node.has("onFailure"))visit(json.createObjectNode().put("type","REST").put("endpointRef",node.path("onFailure").path("endpointRef").asText()),refs);
 }
 public boolean matches(JsonNode published,JsonNode node){
  if(published.path("contract").asInt()!=1)return false;
  try{return published.path("references").path(key(node)).equals(current(node));}catch(RuntimeException unavailable){return false;}
 }
}
