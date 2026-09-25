package dev.routeengine.registry;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.routeengine.api.ApiProblem;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DefinitionRulesTest {
    final ObjectMapper json = new ObjectMapper();
    final DefinitionRules rules = new DefinitionRules(json);
    @Test void AC005_canonicalHashIgnoresObjectKeyOrder() throws Exception {
        assertEquals(rules.hash(json.readTree("{\"b\":1,\"a\":2}")), rules.hash(json.readTree("{\"a\":2,\"b\":1}")));
        assertNotEquals(rules.hash(json.readTree("[1,2]")), rules.hash(json.readTree("[2,1]")));
    }
    @Test void AC008_versionAndIdentityFailClosed() throws Exception {
        var valid=json.readTree("{\"routeId\":\"demo\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"root\":{\"id\":\"root\",\"type\":\"SEQUENCE\",\"children\":[]}}");
        assertDoesNotThrow(()->rules.validate("demo",1,valid));
        assertThrows(ApiProblem.class,()->rules.validate("other",1,valid));
        assertThrows(ApiProblem.class,()->rules.validate("demo",2,valid));
        ((com.fasterxml.jackson.databind.node.ObjectNode)valid).put("engineSemanticsVersion","999");
        assertThrows(ApiProblem.class,()->rules.validate("demo",1,valid));
    }
    @Test void AC008_unknownDefinitionFieldsAndNodesAreRejected() throws Exception {
        var node=json.readTree("{\"routeId\":\"demo\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"root\":{\"id\":\"root\",\"type\":\"SHELL\"}}");
        assertThrows(ApiProblem.class,()->rules.validate("demo",1,node));
        ((com.fasterxml.jackson.databind.node.ObjectNode)node).put("password","DO_NOT_LOG_SECRET");
        assertFalse(assertThrows(ApiProblem.class,()->rules.validate("demo",1,node)).getMessage().contains("DO_NOT_LOG_SECRET"));
    }
}
