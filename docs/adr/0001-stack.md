# ADR 0001 — pinned Java 21 stack

Accepted design baseline, verified 2026-09-25. [Versions](../../config/versions.json),
[download lock](../../config/tool-downloads.json) and [Maven model](../../pom.xml) are machine-readable.

| Component | Fixed version | Official source and reason |
|---|---|---|
| Temurin JDK | 21.0.12.1+1 | [official GA assets](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.12.1%2B1); Java 21 contract baseline |
| Maven / Wrapper | 3.9.11 / 3.3.4 | [Maven release artifact](https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/), [wrapper](https://maven.apache.org/wrapper/); wrapper binary type avoids only-script switching zip to tar when unzip is absent |
| Spring Boot | 3.5.16 | [Java 17–25 and Maven 3.6.3+ supported](https://docs.spring.io/spring-boot/3.5/system-requirements.html); Java 21 compatible GA |
| MariaDB | 11.4.13 | [official Q3 maintenance](https://mariadb.org/mariadb-server-12-3-11-8-11-4-and-10-11-q3-2026-maintenance-releases-and-goodbye-10-6/); [11.4 LTS through 2029](https://mariadb.org/about/) |
| MariaDB JDBC | 3.5.8 | [Boot BOM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-dependencies/3.5.16/spring-boot-dependencies-3.5.16.pom) |
| Flyway core/mysql | 11.8.2 | [official support clarification](https://productsupport.red-gate.com/hc/en-us/community/posts/26900032891421-ETA-for-MariaDB-11-4-Support); override BOM 11.7.2 because MariaDB 11.4 support tested since 11.8.1 |
| Fabric8 Kubernetes client | 7.4.0 | [official client](https://github.com/fabric8io/kubernetes-client); stable API client, explicit Config disables discovery of user contexts |
| JUnit Jupiter / Testcontainers | 5.12.2 / 1.21.4 | Boot BOM fixes test tool versions; actual compatibility established by M1–M4 integration tests, not this table alone |
| kind / Kubernetes / kubectl | 0.33.0 / 1.36.4 / 1.36.4 | [kind official release](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0); node digest pinned, client/server minor match |
| Ansible Runner / Core | 2.4.1 / 2.19.2 | [Runner](https://pypi.org/project/ansible-runner/2.4.1/), [Core](https://pypi.org/project/ansible-core/2.19.2/); M4 will build pinned execution image and validate real playbook artifacts |

Downloads are hashed against official release checksums; bootstrap fails on any mismatch. Maven transitive versions
are fixed by the exact BOM; M1 will resolve and record the actual runtime dependency tree. An imported BOM may list
broker libraries, but this is dependency management and does not install an application dependency or runtime service.
M0 is an environment/design check, not proof of all adapter/runtime integration compatibility.

Only workspace-local tools/caches, no OS package installation. Windows agent invokes the same checkout via WSL2.
This session uses per-command approved execution after intermittent sandbox helper failures; sandbox was not disabled.
