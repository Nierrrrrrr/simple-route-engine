package dev.routeengine;
import dev.routeengine.api.RequestSecurityFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;
class HardeningTest {
 @Test void AC051_roleMatrixRejectsCallerMutation() throws Exception {
  var filter=new RequestSecurityFilter(hash("admin"),hash("caller"),hash("operator"),new ObjectMapper().findAndRegisterModules());
  for(String operation:new String[]{"POST /routes","PATCH /routes/r","DELETE /routes/r","POST /routes/r/versions","PUT /routes/r/versions/1","DELETE /routes/r/versions/1","POST /routes/r/versions/1/publish","PUT /capacity/config","POST /executions/x/recoveries","POST /executions/x/cancel","POST /executions/x/incidents/i/resolve","GET /executions/x/incidents","GET /actuator/metrics","POST /unknown"}){
   var parts=operation.split(" ");String path=parts[1];var req=new MockHttpServletRequest(parts[0],path);
   req.addHeader("Authorization","Bearer caller");var res=new MockHttpServletResponse();
   filter.doFilter(req,res,new MockFilterChain());assertEquals(403,res.getStatus(),path);
  }
 }
 @Test void AC051_missingMalformedAndDuplicateHashesFailClosed(){
  assertThrows(IllegalStateException.class,()->new RequestSecurityFilter("","","",new ObjectMapper().findAndRegisterModules()));
  assertThrows(IllegalStateException.class,()->new RequestSecurityFilter("bad","","",new ObjectMapper().findAndRegisterModules()));
  assertThrows(IllegalStateException.class,()->new RequestSecurityFilter("a".repeat(64),"a".repeat(64),"",new ObjectMapper().findAndRegisterModules()));
 }
 @Test void AC051_rotationPreservesPrincipalAndRevokesOldToken()throws Exception {
  var both=new RequestSecurityFilter(hash("admin"),hash("old")+","+hash("new"),"",new ObjectMapper().findAndRegisterModules());
  for(String token:new String[]{"old","new"}){var req=new MockHttpServletRequest("GET","/routes");req.addHeader("Authorization","Bearer "+token);var res=new MockHttpServletResponse();both.doFilter(req,res,new MockFilterChain());assertEquals(200,res.getStatus());assertEquals("caller",req.getAttribute("actor"));}
  var rotated=new RequestSecurityFilter(hash("admin"),hash("new"),"",new ObjectMapper().findAndRegisterModules());
  var req=new MockHttpServletRequest("GET","/routes");req.addHeader("Authorization","Bearer old");var res=new MockHttpServletResponse();rotated.doFilter(req,res,new MockFilterChain());assertEquals(401,res.getStatus());
 }
 @Test void AC052_catalogRejectsUnknownCommandAndNamespaceEscape()throws Exception {
  var mapper=new ObjectMapper();var file=java.nio.file.Files.createTempFile("catalog-test-",".json");
  try{
   java.nio.file.Files.writeString(file,"{\"command\":\"sh\"}");assertThrows(IllegalArgumentException.class,()->new dev.routeengine.adapters.AdapterCatalog(mapper,file.toString()));
   java.nio.file.Files.writeString(file,"{\"resources\":{\"x\":{\"kind\":\"JOB\",\"namespace\":\"../other\",\"image\":\"x@sha256:"+"a".repeat(64)+"\",\"runId\":\"test\"}}}");assertThrows(IllegalArgumentException.class,()->new dev.routeengine.adapters.AdapterCatalog(mapper,file.toString()));
  }finally{java.nio.file.Files.delete(file);}
 }
 static String hash(String s)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)));}
}
