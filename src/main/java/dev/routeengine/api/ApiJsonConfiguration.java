package dev.routeengine.api;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;
import java.util.List;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Validate JSON token types before Bean Validation and optimistic state comparisons. */
@Configuration
public class ApiJsonConfiguration {
 @Bean Jackson2ObjectMapperBuilderCustomizer strictScalarTypes(){
  return builder->{
   builder.featuresToEnable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
   builder.featuresToDisable(MapperFeature.ALLOW_COERCION_OF_SCALARS,DeserializationFeature.ACCEPT_FLOAT_AS_INT);
   builder.postConfigurer(mapper->{
    var shapes=List.of(CoercionInputShape.Integer,CoercionInputShape.Float,CoercionInputShape.Boolean,CoercionInputShape.String,CoercionInputShape.EmptyString);
    for(var target:List.of(LogicalType.Integer,LogicalType.Boolean,LogicalType.Textual)){
     for(var source:shapes){
      boolean sameType=target==LogicalType.Integer&&source==CoercionInputShape.Integer
        ||target==LogicalType.Boolean&&source==CoercionInputShape.Boolean
        ||target==LogicalType.Textual&&(source==CoercionInputShape.String||source==CoercionInputShape.EmptyString);
      if(!sameType)mapper.coercionConfigFor(target).setCoercion(source,CoercionAction.Fail);
     }
    }
   });
  };
 }
}
