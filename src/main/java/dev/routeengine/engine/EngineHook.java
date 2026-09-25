package dev.routeengine.engine;
/** Optional development-only fault injection; production has no implementation. */
public interface EngineHook {
 default boolean allowClaim(String execution){return true;}
 default void beforeCompletion(EngineService.Work work){}
 default void afterCompletion(EngineService.Work work){}
 default void beforeResult(EngineService.Work work){}
}