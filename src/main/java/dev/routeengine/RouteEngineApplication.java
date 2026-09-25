package dev.routeengine;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class RouteEngineApplication {
 public static void main(String[] args){SpringApplication.run(RouteEngineApplication.class,args);}
 @Bean TransactionTemplate transactionTemplate(PlatformTransactionManager manager){
  var tx=new TransactionTemplate(manager);tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);tx.setTimeout(10);return tx;
 }
}
