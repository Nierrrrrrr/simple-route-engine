package dev.routeengine.adapters;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.net.*;
import java.security.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
/** Deployment-owned configuration, never route-owned URLs, headers, commands or namespaces. */
@Component
public class AdapterCatalog {
 private final ObjectMapper json; private final JsonNode config;
 private final io.fabric8.kubernetes.client.Config kubeConfig;private final String kubeTargetHash;
 public AdapterCatalog(ObjectMapper json,@Value("${route.adapters.config:}") String path) {
  this.json=json;
  try {
   config=path.isBlank()?json.createObjectNode():json.readTree(Files.readString(Path.of(path)));validate();
   if(config.path("resources").size()>0){
    JsonNode k=config.path("kubernetes");String file=k.path("kubeconfig").asText(),context=k.path("context").asText();
    require(!file.isBlank()&&!context.isBlank());Path source=Path.of(file);
    byte[] before=Files.readAllBytes(source);
    kubeConfig=io.fabric8.kubernetes.client.Config.fromKubeconfig(context,source.toFile());
    require(Arrays.equals(before,Files.readAllBytes(source)));
    kubeTargetHash=hash(json.createObjectNode().put("context",context).put("kubeconfigDigest",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(before))));
   }else{kubeConfig=null;kubeTargetHash="";}
  }
  catch(Exception e){throw new IllegalArgumentException("Invalid adapter catalog");}
 }
 private void require(boolean ok){if(!ok)throw new IllegalArgumentException("Invalid adapter catalog");}
 private void validate() throws Exception {
  require(config.isObject());
  for(var e:entries(config.path("endpoints"))) {
   JsonNode c=e.getValue();URI uri=URI.create(c.path("baseUri").asText());
   require(e.getKey().matches("[A-Za-z][A-Za-z0-9_.-]{0,127}"));
   require(uri.getHost()!=null&&uri.getUserInfo()==null&&uri.getFragment()==null&&uri.getQuery()==null);
   require(c.path("allowedHost").asText().equals(uri.getHost()));
   boolean local=Set.of("127.0.0.1","localhost","[::1]").contains(uri.getHost());
   require(uri.getScheme().equals("https")||uri.getScheme().equals("http")&&local&&c.path("allowLoopbackHttp").asBoolean(false));
   require(c.path("timeoutMillis").asInt()>=100&&c.path("timeoutMillis").asInt()<=30000);
   require(c.path("maxResponseBytes").asInt()>=128&&c.path("maxResponseBytes").asInt()<=1048576);
   if(c.has("credentialRef"))require(config.path("credentials").path(c.get("credentialRef").asText()).isTextual());
  }
  for(var e:entries(config.path("resources"))) {
   JsonNode c=e.getValue();
   require(Set.of("DEPLOYMENT","JOB","ANSIBLE").contains(c.path("kind").asText()));
   require(c.path("namespace").asText().matches("[a-z0-9][a-z0-9-]{0,62}"));
   require(c.path("image").asText().matches(".+@sha256:[a-f0-9]{64}"));
   require(c.path("runId").asText().matches("[A-Za-z0-9][A-Za-z0-9-]{0,49}"));
   if(c.path("kind").asText().equals("ANSIBLE")){
    require(c.path("artifactDigest").asText().matches("sha256:[a-f0-9]{64}"));
    require(c.path("pvc").asText().matches("[a-z0-9][a-z0-9-]{0,62}"));
    require(Set.of("probe","wait","fail").contains(c.path("playbook").asText()));
   }
  }
 }
 private List<Map.Entry<String,JsonNode>> entries(JsonNode n){List<Map.Entry<String,JsonNode>> r=new ArrayList<>();n.fields().forEachRemaining(r::add);return r;}
 public JsonNode endpoint(String ref){return config.path("endpoints").path(ref);}
 public JsonNode resource(String ref){return config.path("resources").path(ref);}
 public JsonNode kubernetes(){return config.path("kubernetes");}
 public String kubernetesTargetHash(){return kubeTargetHash;}
 public io.fabric8.kubernetes.client.Config kubernetesConfig(){
  if(kubeConfig==null)throw new IllegalArgumentException("Explicit Kubernetes config required");
  return new io.fabric8.kubernetes.client.Config(kubeConfig);
 }
 public String hash(JsonNode c){
  try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(c.toString().getBytes(StandardCharsets.UTF_8)));}
  catch(Exception e){throw new IllegalStateException("Digest unavailable");}
 }
 public ObjectNode plan(String ref,JsonNode c){return json.createObjectNode().put("ref",ref).put("catalogHash",hash(c));}
 public boolean matches(JsonNode plan,JsonNode config){return plan.path("catalogHash").asText().equals(hash(config));}
 public String credential(JsonNode endpoint) throws Exception {
  if(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Credential file I/O inside transaction");
  if(!endpoint.has("credentialRef"))return "";
  String path=config.path("credentials").path(endpoint.get("credentialRef").asText()).asText();
  if(path.isBlank())throw new IllegalArgumentException("Credential reference unavailable");
  String value=Files.readString(Path.of(path)).strip();
  if(value.isBlank()||value.length()>4096||value.contains("\n")||value.contains("\r"))throw new IllegalArgumentException("Invalid credential");
  return value;
 }
 public JsonNode safeOutput(JsonNode output,String secret) {
  safeFields(output,secret);return output.deepCopy();
 }
 private void safeText(String value,String secret){
  if(!secret.isEmpty()&&value.contains(secret))throw new IllegalArgumentException("Unsafe adapter output");
 }
 private void safeFields(JsonNode n,String secret){
  if(n.isTextual())safeText(n.textValue(),secret);
  else if(n.isValueNode())safeText(n.toString(),secret); // Compare the scalar representation that will be persisted.
  else if(n.isObject())n.fields().forEachRemaining(e->{
   safeText(e.getKey(),secret);
   if(Set.of("password","secret","token","authorization","privatekey","credential").contains(e.getKey().toLowerCase(Locale.ROOT)))throw new IllegalArgumentException("Unsafe adapter output");
   safeFields(e.getValue(),secret);
  });else if(n.isArray())n.forEach(child->safeFields(child,secret));
 }
}
