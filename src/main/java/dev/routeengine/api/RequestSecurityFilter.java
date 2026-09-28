package dev.routeengine.api;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component @Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestSecurityFilter extends OncePerRequestFilter {
 private record Credential(byte[] hash,String actor,String role){}
 private final List<Credential> credentials=new ArrayList<>();private final ObjectMapper json;
 public RequestSecurityFilter(String admin,ObjectMapper json){this(admin,"","",json);}
 @Autowired public RequestSecurityFilter(@Value("${route.auth.admin-token-sha256:}") String admin,
  @Value("${route.auth.caller-token-sha256:}") String caller,@Value("${route.auth.operator-token-sha256:}") String operator,ObjectMapper json){
  this.json=json;if(admin.isBlank())throw new IllegalStateException("Configure authentication before starting");
  Set<String> unique=new HashSet<>();add(admin,"local-admin","admin",unique);add(caller,"caller","caller",unique);add(operator,"operator","operator",unique);
 }
 private void add(String hashes,String actor,String role,Set<String> unique){
  if(hashes.isBlank())return;
  String[] values=hashes.split(",",-1);if(values.length>2)throw new IllegalStateException("At most two rotation hashes per principal");
  for(String h:values){h=h.strip().toLowerCase(Locale.ROOT);if(!h.matches("[a-f0-9]{64}")||!unique.add(h))throw new IllegalStateException("Invalid or ambiguous authentication configuration");credentials.add(new Credential(HexFormat.of().parseHex(h),actor,role));}
 }
 private boolean allowed(String role,String method,String path){
  if(role.equals("admin"))return true;
  if(method.equals("GET")){
   if(path.equals("/actuator/metrics")||path.startsWith("/actuator/metrics/"))return role.equals("operator");
   if(path.matches("/executions/[^/]+/incidents"))return role.equals("operator");
   return path.equals("/capacity")||path.equals("/routes")||path.matches("/routes/[^/]+(?:/versions(?:/[0-9]+)?)?")||path.equals("/admission-requests")||path.matches("/(executions|admission-requests)/[^/]+");
  }
  if(method.equals("POST")&&path.equals("/executions"))return true;
  return role.equals("operator")&&method.equals("POST")&&(path.matches("/executions/[^/]+/(recoveries|cancel)")||path.matches("/executions/[^/]+/incidents/[^/]+/resolve"));
 }
 @Override protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
  String supplied=req.getHeader("X-Request-ID");String rid=supplied!=null&&supplied.matches("[A-Za-z0-9._:-]{1,128}")?supplied:UUID.randomUUID().toString();
  req.setAttribute("requestId",rid);res.setHeader("X-Request-ID",rid);String path=req.getRequestURI();
  if(req.getMethod().equals("GET")&&Set.of("/actuator/health","/actuator/health/liveness","/actuator/health/readiness").contains(path)){chain.doFilter(req,res);return;}
  String auth=req.getHeader("Authorization");Credential found=null;
  if(auth!=null&&auth.startsWith("Bearer ")&&auth.length()<=4096){
   try{byte[] hash=MessageDigest.getInstance("SHA-256").digest(auth.substring(7).getBytes(StandardCharsets.UTF_8));for(var c:credentials)if(MessageDigest.isEqual(c.hash(),hash))found=c;}
   catch(NoSuchAlgorithmException e){throw new IllegalStateException("SHA-256 unavailable",e);}
  }
  if(found==null){deny(res,401,"UNAUTHENTICATED","Valid bearer token required",rid);return;}
  if(!allowed(found.role(),req.getMethod(),path)){deny(res,403,"FORBIDDEN","Role does not permit operation",rid);return;}
  req.setAttribute("actor",found.actor());req.setAttribute("role",found.role());chain.doFilter(req,res);
 }
 private void deny(HttpServletResponse r,int status,String code,String message,String rid)throws IOException{r.setStatus(status);r.setContentType("application/json");json.writeValue(r.getOutputStream(),ApiErrors.body(code,message,rid));}
}
