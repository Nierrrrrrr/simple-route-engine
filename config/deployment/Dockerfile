FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY java /opt/java
COPY app.jar /opt/route/app.jar
USER 1000:1000
ENV ROUTE_BIND_ADDRESS=0.0.0.0 ROUTE_LOG_FILE=/var/log/route/engine.log
ENTRYPOINT ["/opt/java/bin/java","-Duser.timezone=UTC","-jar","/opt/route/app.jar"]
