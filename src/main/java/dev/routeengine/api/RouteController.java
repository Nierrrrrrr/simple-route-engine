package dev.routeengine.api;

import com.fasterxml.jackson.databind.JsonNode;
import dev.routeengine.registry.RouteRegistry;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.http.*;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController @Validated
@RequestMapping(produces=MediaType.APPLICATION_JSON_VALUE)
public class RouteController {
 public record Create(@NotBlank @Pattern(regexp="[a-z][a-z0-9-]{0,63}") String routeId,@NotBlank @Size(max=160) String name){}
 public record Update(@NotBlank @Size(max=160) String name,@NotNull Boolean enabled,@NotNull @Min(0) Long stateVersion){}
 public record Draft(@NotNull JsonNode definition){}
 public record Edit(@NotNull JsonNode definition,@NotNull @Min(0) Long stateVersion){}
 public record State(@NotNull @Min(0) Long stateVersion){}
 private final RouteRegistry registry;
 public RouteController(RouteRegistry registry){this.registry=registry;}
 private String actor(HttpServletRequest r){return (String)r.getAttribute("actor");}
 private String rid(HttpServletRequest r){return (String)r.getAttribute("requestId");}
 @PostMapping("/routes") ResponseEntity<RouteRegistry.Route> create(@Valid @RequestBody Create b,HttpServletRequest r){return ResponseEntity.status(201).body(registry.create(b.routeId(),b.name(),actor(r),rid(r)));}
 @GetMapping("/routes") List<RouteRegistry.Route> list(){return registry.list();}
 @GetMapping("/routes/{routeId}") RouteRegistry.Route get(@PathVariable String routeId){return registry.get(routeId);}
 @PatchMapping("/routes/{routeId}") RouteRegistry.Route update(@PathVariable String routeId,@Valid @RequestBody Update b,HttpServletRequest r){return registry.update(routeId,b.name(),b.enabled(),b.stateVersion(),actor(r),rid(r));}
 @DeleteMapping("/routes/{routeId}") RouteRegistry.Route delete(@PathVariable String routeId,@RequestParam @Min(0) long stateVersion,HttpServletRequest r){return registry.delete(routeId,stateVersion,actor(r),rid(r));}
 @PostMapping("/routes/{routeId}/versions") ResponseEntity<RouteRegistry.Version> draft(@PathVariable String routeId,@Valid @RequestBody Draft b,HttpServletRequest r){return ResponseEntity.status(201).body(registry.draft(routeId,b.definition(),actor(r),rid(r)));}
 @GetMapping("/routes/{routeId}/versions") List<RouteRegistry.Version> versions(@PathVariable String routeId){return registry.versions(routeId);}
 @GetMapping("/routes/{routeId}/versions/{version}") RouteRegistry.Version version(@PathVariable String routeId,@PathVariable @Min(1) int version){return registry.getVersion(routeId,version);}
 @PutMapping("/routes/{routeId}/versions/{version}") RouteRegistry.Version edit(@PathVariable String routeId,@PathVariable @Min(1) int version,@Valid @RequestBody Edit b,HttpServletRequest r){return registry.edit(routeId,version,b.definition(),b.stateVersion(),actor(r),rid(r));}
 @DeleteMapping("/routes/{routeId}/versions/{version}") Map<String,Object> withdraw(@PathVariable String routeId,@PathVariable @Min(1) int version,@RequestParam @Min(0) long stateVersion,HttpServletRequest r){return registry.withdraw(routeId,version,stateVersion,actor(r),rid(r));}
 @PostMapping("/routes/{routeId}/versions/{version}/publish") RouteRegistry.Version publish(@PathVariable String routeId,@PathVariable @Min(1) int version,@Valid @RequestBody State b,HttpServletRequest r){return registry.publish(routeId,version,b.stateVersion(),actor(r),rid(r));}
}
