package dev.routeengine.registry;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.api.ApiProblem;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EngineDslTest {
 final ObjectMapper json=new ObjectMapper();final DefinitionRules rules=new DefinitionRules(json);
 JsonNode parse(String s)throws Exception{return json.readTree(s);}
 ObjectNode route(String children)throws Exception{return (ObjectNode)parse("{\"routeId\":\"demo\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"root\":{\"id\":\"root\",\"type\":\"SEQUENCE\",\"children\":"+children+"}}");}
 String leaf(String id){return "{\"id\":\""+id+"\",\"type\":\"REST\",\"endpointRef\":\"dev.success\"}";}
 void invalid(JsonNode d){assertThrows(ApiProblem.class,()->rules.validate("demo",1,d));}
 @Test void AC031_unknownFieldsNodesDuplicateIdsCyclesAndForwardDependenciesReject()throws Exception{
  for(String child:new String[]{"{\"id\":\"a\",\"type\":\"SHELL\"}","{\"id\":\"a\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"goto\":\"a\"}",leaf("a")+","+leaf("a"),
    "{\"id\":\"a\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"v\":{\"$ref\":\"steps.b.v\"}}},"+leaf("b"),
    "{\"id\":\"a\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"v\":{\"$ref\":\"steps.a.v\"}}}"})invalid(route("["+child+"]"));
 }
 @Test void AC031_parallelDepthBoundsAndSiblingReferencesReject()throws Exception{
  String inner="{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("a")+"]}";
  invalid(route("[{\"id\":\"outer\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+inner+"]}]"));
  invalid(route("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"FIRST_SUCCESS\",\"branches\":["+leaf("a")+"]}]"));
  var r=route("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":[]}]");invalid(r);
  ArrayNode branches=(ArrayNode)r.path("root").path("children").get(0).path("branches");for(int i=0;i<11;i++)branches.add(parse(leaf("a"+i)));invalid(r);
 }
 @Test void AC031_typedExpressionAndReferencesRequireDeclaredShapes()throws Exception{
  for(String condition:new String[]{"{\"field\":\"input.flag\",\"operator\":\"eval\",\"value\":true}","{\"field\":\"input.flag\",\"operator\":\"LT\",\"value\":true}","{\"field\":\"input.flag\",\"operator\":\"EQ\",\"value\":\"true\"}","{\"field\":\"steps.future.flag\",\"operator\":\"EQ\",\"value\":true}"}){
   var d=route("[{\"id\":\"choice\",\"type\":\"CONDITION\",\"condition\":"+condition+",\"then\":"+leaf("a")+",\"else\":"+leaf("b")+"}]");
   d.set("inputSchema",parse("{\"type\":\"object\",\"properties\":{\"flag\":{\"type\":\"boolean\"}},\"required\":[\"flag\"]}"));invalid(d);
  }
 }
 @Test void AC031_retryBoundsAndUnknownPoliciesReject()throws Exception{
  for(String retry:new String[]{"{\"maxAttempts\":0,\"maxElapsedSeconds\":5,\"backoffSeconds\":1}","{\"maxAttempts\":101,\"maxElapsedSeconds\":5,\"backoffSeconds\":1}","{\"maxAttempts\":2,\"maxElapsedSeconds\":0,\"backoffSeconds\":1}","{\"maxAttempts\":2,\"maxElapsedSeconds\":5,\"backoffSeconds\":-1}","{\"maxAttempts\":2,\"maxElapsedSeconds\":5,\"backoffSeconds\":3,\"maxBackoffSeconds\":1}"}){
   var d=route("["+leaf("a")+"]");((ObjectNode)d.path("root").path("children").get(0)).set("retry",parse(retry));invalid(d);
  }
 }
 @Test void AC031_acceptsTypedPriorOutputAndRejectsSharedBranchDependency()throws Exception{
  String producer="{\"id\":\"a\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"outputSchema\":{\"type\":\"object\",\"properties\":{\"v\":{\"type\":\"integer\"}},\"required\":[\"v\"]}}";
  String consumer="{\"id\":\"b\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"v\":{\"$ref\":\"steps.a.v\"}}}";
  var d=route("["+producer+","+consumer+"]");assertDoesNotThrow(()->rules.validate("demo",1,d));
  invalid(route("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+producer+","+consumer+"]}]"));
 }
 @Test void AC031_nodeCountAndStructureDepthBounded()throws Exception{
  var d=route("[]");ArrayNode children=(ArrayNode)d.path("root").path("children");for(int i=0;i<100;i++)children.add(parse(leaf("n"+i)));invalid(d);
  String inner=leaf("end");for(int i=0;i<22;i++)inner="{\"id\":\"s"+i+"\",\"type\":\"SEQUENCE\",\"children\":["+inner+"]}";invalid(route("["+inner+"]"));
 }

 @Test void AC031_optionalOutputCannotBeUsedAsUnconditionalRequiredBinding()throws Exception{
  String producer="{\"id\":\"a\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"outputSchema\":{\"type\":\"object\",\"properties\":{\"v\":{\"type\":\"integer\"}}}}";
  String consumer="{\"id\":\"b\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"v\":{\"$ref\":\"steps.a.v\"}}}";
  invalid(route("["+producer+","+consumer+"]"));
 }
}