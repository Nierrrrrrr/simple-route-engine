package dev.routeengine.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component @Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestSecurityFilter extends OncePerRequestFilter {
 private final byte[] adminHash;
 private final ObjectMapper json;
 public RequestSecurityFilter(@Value("${route.auth.admin-token-sha256}") String hash,ObjectMapper json){
  if(!hash.matches("[a-fA-F0-9]{64}"))throw new IllegalStateException("Configure an SHA-256 admin token hash before starting");
  this.adminHash=HexFormat.of().parseHex(hash);this.json=json;
 }
 @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain)throws ServletException,IOException{
  String supplied=request.getHeader("X-Request-ID");
  String requestId=supplied!=null && supplied.matches("[A-Za-z0-9._:-]{1,128}")?supplied:UUID.randomUUID().toString();
  request.setAttribute("requestId",requestId);response.setHeader("X-Request-ID",requestId);
  if(request.getRequestURI().equals("/actuator/health")){chain.doFilter(request,response);return;}
  String auth=request.getHeader("Authorization");
  boolean valid=false;
  if(auth!=null && auth.startsWith("Bearer ") && auth.length()<=4096){
   try{valid=MessageDigest.isEqual(adminHash,MessageDigest.getInstance("SHA-256").digest(auth.substring(7).getBytes(StandardCharsets.UTF_8)));}
   catch(NoSuchAlgorithmException e){throw new IllegalStateException("SHA-256 unavailable",e);}
  }
  if(!valid){response.setStatus(401);response.setContentType("application/json");json.writeValue(response.getOutputStream(),ApiErrors.body("UNAUTHENTICATED","Valid bearer token required",requestId));return;}
  request.setAttribute("actor","local-admin");chain.doFilter(request,response);
 }
}
