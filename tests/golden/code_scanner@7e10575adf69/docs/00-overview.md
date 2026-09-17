# tree — architecture overview

Reconstructed by CDP at commit `<HEAD>`. Every claim below carries a `file:line` citation that a Python verifier confirmed against the file.

> **Coverage: 0.0%** — 0 of 4728 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/(.github+3)`, `root/(build+5)`, `root/(files)`, `root/.claude`, `root/.cursor`, `root/automation`, `root/automation/api-automation/(files+10)`, `root/automation/api-automation/src/main/java/com/rms/uds/tests`.

## Census

| | |
|---|---|
| Tracked files | 4,728 |
| Files on disk | 4,729 (**1.0x**) |
| Inventory source | `git` |
| Modules | 62 |
| Symbols declared | 20,255 |
| HTTP routes | 565 |

### Generated modules

- **`automation`** — 2 tracked file(s) against 44 on disk. Generated at build time; described by its build contract rather than read.
- **`client-java`** — 3 tracked file(s) against 420 on disk. Generated at build time; described by its build contract rather than read.
- **`exposure-snapshot/snapshot-legacy`** — 1 tracked file(s) against 58 on disk. Generated at build time; described by its build contract rather than read.
- **`sql-pool`** — 20 tracked file(s) against 477 on disk. Generated at build time; described by its build contract rather than read.

## Naming

The facts that cost a newcomer an afternoon and appear in no artifact.

- The build's root project is named 'spm', which appears in no directory name; every module directory is '?...'. Build logs, metrics and the OpenAPI title use 'spm'. — `sql-pool/settings.gradle:1`
- 1 source files declare a package whose text and directory path do not correspond (e.g. directory 'com/rms/unifiedstore/snapshot/common/constants' declares 'package com.rms.unifiedstore.constants'). Any path-to-package inference produces names that match nothing; on a case-insensitive filesystem this is invisible. — `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/constants/CacheConstants.java:3` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/errorhandling/SPMExceptionMapper.java:11`

## Deployable units

- automation/api-automation is packaged as its own container image; its entry command is ["java", \. — `automation/api-automation/Dockerfile:25`
- exposure-snapshot is packaged as its own container image; its entry command is ["/bin/bash", "-e", "run-migrations.sh"]. — `exposure-snapshot/domain-data-migration/Dockerfile:30`
- exposure-snapshot/download-exposure is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/download-exposure/Dockerfile:23`
- exposure-snapshot/entity-variation-task is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/entity-variation-task/Dockerfile:19`
- exposure-snapshot/snapshot-api is packaged as its own container image; its entry command is /api-run. — `exposure-snapshot/snapshot-api/Dockerfile:17`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation is packaged as its own container image; its entry command is /runWorkflow.sh. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation/Dockerfile:12`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-partition is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition/Dockerfile:17`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-task is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/Dockerfile:21`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-transform is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform/Dockerfile:18`
- exposure-snapshot/snapshot-migration is packaged as its own container image; its entry command is ["/bin/bash", "-e", "run-flyway-migrations.sh"]. — `exposure-snapshot/snapshot-migration/Dockerfile:38`
- exposure-snapshot/snapshot-smoketest is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/snapshot-smoketest/Dockerfile:17`
- exposure-snapshot/snapshot-task-create is packaged as its own container image; its entry command is java $JAVA_OPTS /opt/snapshot-task-create.jar. — `exposure-snapshot/snapshot-task-create/Dockerfile:12`
- exposure-snapshot/snapshot-task-delete is packaged as its own container image; its entry command is java $JAVA_OPTS \. — `exposure-snapshot/snapshot-task-delete/Dockerfile:21`
- (root) is packaged as its own container image; its entry command is ["dotnet", "/app/RMS.UnifiedStore.Service.ManagedSql/RMS.UnifiedStore.Service.ManagedSql.dll"]. — `managed-sql/Dockerfile:9`
- ms-sql-java/downgrade-processor is packaged as its own container image; its entry command is java -jar /opt/downgrade-processor.jar. — `ms-sql-java/downgrade-processor/Dockerfile:22`
- (root) is packaged as its own container image; its entry command is ["dotnet", "/app/RMS.UnifiedStore.Service.Api/RMS.UnifiedStore.Service.Api.dll"]. — `service-api/docker/Dockerfile:53`
- sql-pool/sql-pool-api is packaged as its own container image; its entry command is sql-pool-api/bin/sql-pool-api server dropwizard-service-config.yml. — `sql-pool/sql-pool-api/Dockerfile:23`
- sql-pool/sql-pool-manager is packaged as its own container image; its entry command is sql-pool-manager/bin/sql-pool-manager server dropwizard-service-config.yml. — `sql-pool/sql-pool-manager/Dockerfile:23`
- sql-pool/sql-pool-setup is packaged as its own container image; its entry command is java -cp "*" rms.unifiedstore.sqlpool.setup.SetupApplication. — `sql-pool/sql-pool-setup/Dockerfile:16`
- sql-pool/sql-pool-smoketest is packaged as its own container image; its entry command is sql-pool-smoketest/bin/sql-pool-smoketest rms.unifiedstore.sqlpool.test.SqlPoolTestSuite. — `sql-pool/sql-pool-smoketest/Dockerfile:22`
- GenerateExposureSchemaFromParquetFiles declares a process entry point in exposure-snapshot/snapshot-developer-utils; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-developer-utils/src/main/java/GenerateExposureSchemaFromParquetFiles.java:143`
- Program declares a process entry point in catalog-service/RMS.UnifiedStore.Service.Catalog; it is one of the repository's separately-startable units. — `catalog-service/RMS.UnifiedStore.Service.Catalog/Program.cs:31`
- Program declares a process entry point in service-api/RMS.UnifiedStore.Service.Api; it is one of the repository's separately-startable units. — `service-api/RMS.UnifiedStore.Service.Api/Program.cs:34`
- DeleteSnapshotTask declares a process entry point in exposure-snapshot/snapshot-task-delete; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:126`
- DowngradeProcessor declares a process entry point in ms-sql-java/downgrade-processor; it is one of the repository's separately-startable units. — `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/DowngradeProcessor.java:32`
- AccountSnapshotEngine declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/engine/AccountSnapshotEngine.java:9`
- PortfolioSnapshotEngine declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/engine/PortfolioSnapshotEngine.java:9`
- SnapshotEngine declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/engine/SnapshotEngine.java:14`
- ExposureBundleServiceIT declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/test/java/com/rms/unifiedstore/entityvariation/integration/ExposureBundleServiceIT.java:17`
- SnapshotPartitionTask declares a process entry point in exposure-snapshot/snapshot-legacy/snapshot-legacy-partition; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition/src/main/java/com/rms/unifiedstore/partition/SnapshotPartitionTask.java:10`
- APIApplication declares a process entry point in exposure-snapshot/snapshot-api; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:102`
- GetS2STokenApp declares a process entry point in exposure-snapshot/snapshot-api; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/GetS2STokenApp.java:10`
- SnapshotApplication declares a process entry point in exposure-snapshot/snapshot-task-create; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/SnapshotApplication.java:25`
- AutomationDebugTool declares a process entry point in client-java/uds-client-integration-tests; it is one of the repository's separately-startable units. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/AutomationDebugTool.java:81`
- PipelineTestRunner declares a process entry point in client-java/uds-client-integration-tests; it is one of the repository's separately-startable units. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/PipelineTestRunner.java:15`
- TransformEdmTask declares a process entry point in exposure-snapshot/snapshot-legacy/snapshot-legacy-transform; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform/src/main/java/com/rms/unifiedstore/transform/TransformEdmTask.java:10`
- exposure-snapshot/domain-data-migration declares a process entry point in exposure-snapshot; it is one of the repository's separately-startable units. — `exposure-snapshot/domain-data-migration/Dockerfile:30`
- managed-sql declares a process entry point in (root); it is one of the repository's separately-startable units. — `managed-sql/Dockerfile:9`
- winrm_script declares a process entry point in ms-sql-java/downgrade-processor; it is one of the repository's separately-startable units. — `ms-sql-java/downgrade-processor/scripts/winrm_script.py:449`
- SqlPoolApplication declares a process entry point in sql-pool/sql-pool-api; it is one of the repository's separately-startable units. — `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/SqlPoolApplication.java:33`
- RegenerateSchemaBaseline declares a process entry point in sql-pool/sql-pool-integrationtest; it is one of the repository's separately-startable units. — `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/schema/RegenerateSchemaBaseline.java:28`
- SqlPoolQuartzJobsApplication declares a process entry point in sql-pool/sql-pool-manager; it is one of the repository's separately-startable units. — `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/SqlPoolQuartzJobsApplication.java:33`
- SetupApplication declares a process entry point in sql-pool/sql-pool-setup; it is one of the repository's separately-startable units. — `sql-pool/sql-pool-setup/src/main/java/RMS/UnifiedStore/sqlpool/setup/SetupApplication.java:14`
- service-api/docker declares a process entry point in (root); it is one of the repository's separately-startable units. — `service-api/docker/Dockerfile:53`

## Module dependency graph

Built twice — from build manifests (**declared**) and from import statements (**observed**) — because the divergence between them is a finding, not an error to reconcile.

| Source | Inter-module edges |
|---|---|
| Declared (build manifests) | 54 |
| Observed (imports) | 124 |

Observed dependency levels (each depends only on those above it):

```
L0  (root), automation, automation/api-automation, client-dotnet/RMS.UnifiedStore.Client, client-java, client-java/client-core, core/RMS.UnifiedStore.Core, exposure-snapshot, exposure-snapshot/entity-variation-task, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy, exposure-snapshot/swagger-resource, managed-sql/RMS.UnifiedStore.Service.ManagedSql, ms-sql-java, ms-sql-java/downgrade-processor, sql-pool, sql-pool/sql-pool-api-client, sql-pool/sql-pool-common
L1  client-java/eih-client, client-java/uds-client, core/RMS.UnifiedStore.Core.App, core/RMS.UnifiedStore.Core.Tests, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-developer-utils, exposure-snapshot/snapshot-legacy/snapshot-legacy-partition, exposure-snapshot/snapshot-legacy/snapshot-legacy-transform, exposure-snapshot/snapshot-migration, exposure-snapshot/snapshot-sdk, managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests, sql-pool/sql-pool-dal, sql-pool/sql-pool-provision, sql-pool/sql-pool-setup, tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB, tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests
L2  catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core.App.Tests, exposure-snapshot/idempotency-filter, exposure-snapshot/snapshot-filter-query-service, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-smoketest, exposure-snapshot/snapshot-task-create, exposure-snapshot/snapshot-task-delete, sql-pool/sql-pool-integrationtest, sql-pool/sql-pool-service, sql-pool/sql-pool-smoketest
L3  catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, exposure-snapshot/download-exposure, exposure-snapshot/snapshot-workflow-service, service-api/RMS.UnifiedStore.Service.Api.Common, sql-pool/sql-pool-api, sql-pool/sql-pool-manager
L4  catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests, catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Integration.Tests
L5  catalog-service/RMS.UnifiedStore.Service.Catalog.Tests, client-java/uds-client-integration-tests, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, service-api/RMS.UnifiedStore.Service.Api.Tests
```

### Imported but not declared

These compile by transitive resolution and will break on a dependency bump.

- `catalog-service/RMS.UnifiedStore.Service.Catalog` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `catalog-service/RMS.UnifiedStore.Service.Catalog` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`
- `catalog-service/RMS.UnifiedStore.Service.Catalog` -> `core/RMS.UnifiedStore.Core`
- `catalog-service/RMS.UnifiedStore.Service.Catalog` -> `core/RMS.UnifiedStore.Core.App`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` -> `core/RMS.UnifiedStore.Core`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` -> `core/RMS.UnifiedStore.Core.App`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests` -> `core/RMS.UnifiedStore.Core`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` -> `core/RMS.UnifiedStore.Core`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` -> `core/RMS.UnifiedStore.Core.App`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests` -> `core/RMS.UnifiedStore.Core`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` -> `core/RMS.UnifiedStore.Core`
- `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` -> `core/RMS.UnifiedStore.Core.App`
- `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`
- `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` -> `core/RMS.UnifiedStore.Core`
- `client-java/uds-client` -> `exposure-snapshot/ods-domain-data`
- `client-java/uds-client` -> `exposure-snapshot/snapshot-sdk`
- `client-java/uds-client-integration-tests` -> `client-java/client-core`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/download-exposure`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-common`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-task`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-sdk`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-smoketest`
- `core/RMS.UnifiedStore.Core.App` -> `core/RMS.UnifiedStore.Core`
- `core/RMS.UnifiedStore.Core.App.Tests` -> `core/RMS.UnifiedStore.Core`
- `core/RMS.UnifiedStore.Core.App.Tests` -> `core/RMS.UnifiedStore.Core.App`
- `core/RMS.UnifiedStore.Core.Tests` -> `core/RMS.UnifiedStore.Core`
- `exposure-snapshot/download-exposure` -> `client-java/client-core`
- `exposure-snapshot/download-exposure` -> `client-java/uds-client`
- `exposure-snapshot/download-exposure` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `exposure-snapshot/idempotency-filter` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/ods-domain-data` -> `client-java/uds-client`
- `exposure-snapshot/ods-domain-data` -> `exposure-snapshot/snapshot-sdk`
- `exposure-snapshot/snapshot-api` -> `client-java/client-core`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/snapshot-filter-query-service`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `client-java/uds-client`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `exposure-snapshot/download-exposure`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-task`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `exposure-snapshot/snapshot-sdk`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` -> `exposure-snapshot/snapshot-smoketest`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `client-java/uds-client`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/download-exposure`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/snapshot-smoketest`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/snapshot-workflow-service`
- `exposure-snapshot/snapshot-sdk` -> `client-java/client-core`
- `exposure-snapshot/snapshot-smoketest` -> `client-java/client-core`
- `exposure-snapshot/snapshot-workflow-service` -> `exposure-snapshot/snapshot-common`
- `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests` -> `managed-sql/RMS.UnifiedStore.Service.ManagedSql`
- `service-api/RMS.UnifiedStore.Service.Api` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `service-api/RMS.UnifiedStore.Service.Api` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`
- `service-api/RMS.UnifiedStore.Service.Api` -> `core/RMS.UnifiedStore.Core`
- `service-api/RMS.UnifiedStore.Service.Api` -> `core/RMS.UnifiedStore.Core.App`
- `service-api/RMS.UnifiedStore.Service.Api` -> `service-api/RMS.UnifiedStore.Service.Api.Common`
- `service-api/RMS.UnifiedStore.Service.Api.Common` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `service-api/RMS.UnifiedStore.Service.Api.Common` -> `core/RMS.UnifiedStore.Core`
- `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests` -> `core/RMS.UnifiedStore.Core`
- `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests` -> `service-api/RMS.UnifiedStore.Service.Api.Common`
- `service-api/RMS.UnifiedStore.Service.Api.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`
- `service-api/RMS.UnifiedStore.Service.Api.Tests` -> `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`
- `service-api/RMS.UnifiedStore.Service.Api.Tests` -> `core/RMS.UnifiedStore.Core`
- `service-api/RMS.UnifiedStore.Service.Api.Tests` -> `core/RMS.UnifiedStore.Core.App`
- `service-api/RMS.UnifiedStore.Service.Api.Tests` -> `service-api/RMS.UnifiedStore.Service.Api`
- `service-api/RMS.UnifiedStore.Service.Api.Tests` -> `service-api/RMS.UnifiedStore.Service.Api.Common`
- `tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB` -> `core/RMS.UnifiedStore.Core`
- `tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests` -> `core/RMS.UnifiedStore.Core`

### Declared but never imported

Candidate stale dependencies. Note that a dependency on a module whose sources are generated at build time will appear here legitimately — the imports exist, but not in git.

- `exposure-snapshot` -> `client-java/uds-client`
- `exposure-snapshot/download-exposure` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-sdk` -> `exposure-snapshot/snapshot-filter-query-service`
- `exposure-snapshot/snapshot-smoketest` -> `exposure-snapshot/snapshot-common`
- `sql-pool/sql-pool-integrationtest` -> `sql-pool/sql-pool-api-client`
- `sql-pool/sql-pool-setup` -> `sql-pool/sql-pool-provision`
- `sql-pool/sql-pool-smoketest` -> `sql-pool/sql-pool-api-client`

## Modules

| Module | Files | LOC | Depends on | Depended on by |
|---|---|---|---|---|
| [`service-api/RMS.UnifiedStore.Service.Api`](modules/service-api__RMS.UnifiedStore.Service.Api.md) | 1047 | 615,149 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App, service-api/RMS.UnifiedStore.Service.Api.Common | service-api/RMS.UnifiedStore.Service.Api.Tests |
| [`managed-sql/RMS.UnifiedStore.Service.ManagedSql`](modules/managed-sql__RMS.UnifiedStore.Service.ManagedSql.md) | 518 | 73,362 | — | managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Common`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Common.md) | 375 | 41,806 | core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App | catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Tests, catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Common, service-api/RMS.UnifiedStore.Service.Api.Integration.Tests, service-api/RMS.UnifiedStore.Service.Api.Tests |
| [`client-java/uds-client`](modules/client-java__uds-client.md) | 248 | 36,295 | client-java/client-core, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-sdk | client-java/uds-client-integration-tests, exposure-snapshot/download-exposure, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-task-create |
| [`exposure-snapshot/snapshot-common`](modules/exposure-snapshot__snapshot-common.md) | 220 | 16,249 | — | client-java/uds-client-integration-tests, exposure-snapshot/download-exposure, exposure-snapshot/idempotency-filter, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-developer-utils, exposure-snapshot/snapshot-filter-query-service, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-legacy/snapshot-legacy-partition, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-legacy/snapshot-legacy-transform, exposure-snapshot/snapshot-migration, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-task-create, exposure-snapshot/snapshot-task-delete, exposure-snapshot/snapshot-workflow-service |
| [`exposure-snapshot/entity-variation-task`](modules/exposure-snapshot__entity-variation-task.md) | 164 | 16,916 | — | — |
| [`service-api/RMS.UnifiedStore.Service.Api.Tests`](modules/service-api__RMS.UnifiedStore.Service.Api.Tests.md) | 162 | 51,363 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Common | — |
| [`client-java/uds-client-integration-tests`](modules/client-java__uds-client-integration-tests.md) | 128 | 26,418 | client-java/client-core, client-java/eih-client, client-java/uds-client, exposure-snapshot/download-exposure, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-smoketest | — |
| [`exposure-snapshot/snapshot-api`](modules/exposure-snapshot__snapshot-api.md) | 124 | 17,382 | client-java/client-core, client-java/uds-client, exposure-snapshot/idempotency-filter, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-filter-query-service, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-workflow-service, exposure-snapshot/swagger-resource | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.md) | 115 | 11,133 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App | catalog-service/RMS.UnifiedStore.Service.Catalog.Tests |
| [`managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests`](modules/managed-sql__RMS.UnifiedStore.Service.ManagedSql.Tests.md) | 108 | 31,246 | managed-sql/RMS.UnifiedStore.Service.ManagedSql | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Engine.md) | 103 | 9,068 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App | catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Tests, catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Tests |
| [`sql-pool/sql-pool-common`](modules/sql-pool__sql-pool-common.md) | 90 | 6,400 | — | sql-pool/sql-pool-api, sql-pool/sql-pool-dal, sql-pool/sql-pool-integrationtest, sql-pool/sql-pool-manager, sql-pool/sql-pool-provision, sql-pool/sql-pool-service, sql-pool/sql-pool-setup, sql-pool/sql-pool-smoketest |
| [`sql-pool/sql-pool-integrationtest`](modules/sql-pool__sql-pool-integrationtest.md) | 85 | 28,758 | sql-pool/sql-pool-common, sql-pool/sql-pool-dal | — |
| [`core/RMS.UnifiedStore.Core`](modules/core__RMS.UnifiedStore.Core.md) | 78 | 2,855 | — | catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Tests, catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli, core/RMS.UnifiedStore.Core.App, core/RMS.UnifiedStore.Core.App.Tests, core/RMS.UnifiedStore.Core.Tests, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Common, service-api/RMS.UnifiedStore.Service.Api.Integration.Tests, service-api/RMS.UnifiedStore.Service.Api.Tests, tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB, tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests |
| [`sql-pool/sql-pool-manager`](modules/sql-pool__sql-pool-manager.md) | 74 | 8,554 | sql-pool/sql-pool-common, sql-pool/sql-pool-provision, sql-pool/sql-pool-service | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Common.Tests.md) | 67 | 10,656 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Engine.Tests.md) | 57 | 6,789 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, core/RMS.UnifiedStore.Core | — |
| [`sql-pool/sql-pool-provision`](modules/sql-pool__sql-pool-provision.md) | 52 | 2,420 | sql-pool/sql-pool-common | sql-pool/sql-pool-manager, sql-pool/sql-pool-smoketest |
| [`exposure-snapshot/snapshot-sdk`](modules/exposure-snapshot__snapshot-sdk.md) | 50 | 7,932 | client-java/client-core, client-java/uds-client, exposure-snapshot/snapshot-common | client-java/uds-client, client-java/uds-client-integration-tests, exposure-snapshot/download-exposure, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-smoketest, exposure-snapshot/snapshot-task-delete |
| [`exposure-snapshot`](modules/exposure-snapshot.md) | 49 | 247,920 | — | — |
| [`sql-pool/sql-pool-api`](modules/sql-pool__sql-pool-api.md) | 49 | 4,038 | sql-pool/sql-pool-common, sql-pool/sql-pool-service | — |
| [`sql-pool/sql-pool-setup`](modules/sql-pool__sql-pool-setup.md) | 49 | 1,759 | sql-pool/sql-pool-common | — |
| [`exposure-snapshot/snapshot-smoketest`](modules/exposure-snapshot__snapshot-smoketest.md) | 43 | 4,784 | client-java/client-core, exposure-snapshot/snapshot-sdk | client-java/uds-client-integration-tests, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-task |
| [`automation/api-automation`](modules/automation__api-automation.md) | 42 | 7,178 | — | — |
| [`catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli`](modules/catalog-service__RMS.UnifiedStore.Tools.Catalog.Cli.md) | 39 | 4,484 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, core/RMS.UnifiedStore.Core | — |
| [`exposure-snapshot/snapshot-workflow-service`](modules/exposure-snapshot__snapshot-workflow-service.md) | 32 | 2,621 | exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-filter-query-service | exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-legacy/snapshot-legacy-task |
| [`exposure-snapshot/ods-domain-data`](modules/exposure-snapshot__ods-domain-data.md) | 31 | 2,550 | client-java/uds-client, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-sdk | client-java/uds-client, exposure-snapshot/idempotency-filter, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-filter-query-service |
| [`client-java/client-core`](modules/client-java__client-core.md) | 30 | 1,595 | — | client-java/eih-client, client-java/uds-client, client-java/uds-client-integration-tests, exposure-snapshot/download-exposure, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-smoketest |
| [`ms-sql-java/downgrade-processor`](modules/ms-sql-java__downgrade-processor.md) | 26 | 57,123 | — | — |
| [`core/RMS.UnifiedStore.Core.App`](modules/core__RMS.UnifiedStore.Core.App.md) | 23 | 924 | core/RMS.UnifiedStore.Core | catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, catalog-service/RMS.UnifiedStore.Service.Catalog.Tests, core/RMS.UnifiedStore.Core.App.Tests, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Tests |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-task`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-task.md) | 23 | 4,670 | client-java/uds-client, exposure-snapshot/download-exposure, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-smoketest, exposure-snapshot/snapshot-workflow-service | client-java/uds-client-integration-tests, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation |
| [`exposure-snapshot/swagger-resource`](modules/exposure-snapshot__swagger-resource.md) | 23 | 11,889 | — | exposure-snapshot/snapshot-api |
| [`sql-pool/sql-pool-service`](modules/sql-pool__sql-pool-service.md) | 23 | 5,821 | sql-pool/sql-pool-common, sql-pool/sql-pool-dal | sql-pool/sql-pool-api, sql-pool/sql-pool-manager |
| [`exposure-snapshot/snapshot-task-create`](modules/exposure-snapshot__snapshot-task-create.md) | 22 | 1,430 | client-java/uds-client, exposure-snapshot/snapshot-common | — |
| [`sql-pool/sql-pool-dal`](modules/sql-pool__sql-pool-dal.md) | 21 | 1,801 | sql-pool/sql-pool-common | sql-pool/sql-pool-integrationtest, sql-pool/sql-pool-service |
| [`sql-pool`](modules/sql-pool.md) | 20 | 2,497 | — | — |
| [`exposure-snapshot/download-exposure`](modules/exposure-snapshot__download-exposure.md) | 19 | 3,510 | client-java/client-core, client-java/uds-client, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-sdk | client-java/uds-client-integration-tests, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-task |
| [`exposure-snapshot/snapshot-filter-query-service`](modules/exposure-snapshot__snapshot-filter-query-service.md) | 19 | 2,217 | exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-common | exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-workflow-service |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-core`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-core.md) | 18 | 992 | exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-sdk | client-java/uds-client-integration-tests, exposure-snapshot/download-exposure, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-task |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Tests`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Tests.md) | 17 | 3,000 | catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App | — |
| [`exposure-snapshot/snapshot-migration`](modules/exposure-snapshot__snapshot-migration.md) | 15 | 732 | exposure-snapshot/snapshot-common | — |
| [`service-api/RMS.UnifiedStore.Service.Api.Integration.Tests`](modules/service-api__RMS.UnifiedStore.Service.Api.Integration.Tests.md) | 15 | 2,305 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core, service-api/RMS.UnifiedStore.Service.Api.Common | — |
| [`sql-pool/sql-pool-smoketest`](modules/sql-pool__sql-pool-smoketest.md) | 12 | 887 | sql-pool/sql-pool-common, sql-pool/sql-pool-provision | — |
| [`client-java/eih-client`](modules/client-java__eih-client.md) | 11 | 443 | client-java/client-core | client-java/uds-client-integration-tests |
| [`tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB`](modules/tests__performance__catalog-data-model__RMS.UnifiedStore.Tests.Performance.DataModel.DB.md) | 9 | 365 | core/RMS.UnifiedStore.Core | — |
| [`core/RMS.UnifiedStore.Core.Tests`](modules/core__RMS.UnifiedStore.Core.Tests.md) | 8 | 1,093 | core/RMS.UnifiedStore.Core | — |
| [`exposure-snapshot/idempotency-filter`](modules/exposure-snapshot__idempotency-filter.md) | 8 | 478 | exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-common | exposure-snapshot/snapshot-api |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-accumulation.md) | 8 | 605 | client-java/uds-client, exposure-snapshot/download-exposure, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-smoketest | — |
| [`exposure-snapshot/snapshot-task-delete`](modules/exposure-snapshot__snapshot-task-delete.md) | 6 | 428 | exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-sdk | — |
| [`service-api/RMS.UnifiedStore.Service.Api.Common`](modules/service-api__RMS.UnifiedStore.Service.Api.Common.md) | 5 | 311 | catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core | service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Integration.Tests, service-api/RMS.UnifiedStore.Service.Api.Tests |
| [`core/RMS.UnifiedStore.Core.App.Tests`](modules/core__RMS.UnifiedStore.Core.App.Tests.md) | 4 | 226 | core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App | — |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-partition`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-partition.md) | 4 | 163 | exposure-snapshot/snapshot-common | — |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-transform`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-transform.md) | 4 | 196 | exposure-snapshot/snapshot-common | — |
| [`ms-sql-java`](modules/ms-sql-java.md) | 4 | 146 | — | — |
| [`client-java`](modules/client-java.md) | 3 | 193 | — | — |
| [`automation`](modules/automation.md) | 2 | 40 | — | — |
| [`client-dotnet/RMS.UnifiedStore.Client`](modules/client-dotnet__RMS.UnifiedStore.Client.md) | 2 | 15 | — | — |
| [`exposure-snapshot/snapshot-developer-utils`](modules/exposure-snapshot__snapshot-developer-utils.md) | 2 | 189 | exposure-snapshot/snapshot-common | — |
| [`sql-pool/sql-pool-api-client`](modules/sql-pool__sql-pool-api-client.md) | 2 | 62 | — | — |
| [`tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests`](modules/tests__performance__catalog-data-model__RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests.md) | 2 | 86 | core/RMS.UnifiedStore.Core | — |
| [`exposure-snapshot/snapshot-legacy`](modules/exposure-snapshot__snapshot-legacy.md) | 1 | 215 | — | — |

## HTTP surface

| Verb | Route | Handler | Declared as | Evidence |
|---|---|---|---|---|
| `GET` | `/` | `ExposureBundlesResource#getExposureBundleTableSets` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:570` |
| `GET` | `/` | `ExposureBundlesResource#getExposureBundles` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:458` |
| `GET` | `/` | `ExposureVariationsResource#getExposureVariations` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureVariationsResource.java:70` |
| `GET` | `/` | `VariationJobsResource#getExposureVariationJobs` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:199` |
| `POST` | `/` | `ExposureBundlesResource#createExposureBundle` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:103` |
| `POST` | `/` | `VariationJobsResource#postEntityVariation` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:103` |
| `GET` | `/health` | `SqlPoolHealthCheckResource#health` | `${ApiConstants.SQL_POOL_HEALTH_PATH}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/SqlPoolHealthCheckResource.java:43` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:6` |
| `GET` | `/health` | `SqlPoolQuartzHealthCheckResource#health` | `${ApiConstants.SQL_POOL_HEALTH_PATH}` | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/resources/SqlPoolQuartzHealthCheckResource.java:38` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:6` |
| `GET` | `/openapi` | `SwaggerResource#get` | literal | `exposure-snapshot/swagger-resource/src/main/java/com/rms/utils/swagger/SwaggerResource.java:20` |
| `DELETE` | `/tenant/{tenantId}` | `TenantProvisioningResource#deleteProvisionsForTenant` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/TenantProvisioningResource.java:140` |
| `GET` | `/tenant/{tenantId}` | `TenantProvisioningResource#getProvisionStatusForTenant` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/TenantProvisioningResource.java:54` |
| `POST` | `/tenant/{tenantId}` | `TenantProvisioningResource#provisionForTenant` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/TenantProvisioningResource.java:101` |
| `POST` | `/upload` | `ExposureBundlesResource#prepareUploadExposureBundle` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:187` |
| `GET` | `/v1/pools` | `PoolConfigResource#getPoolConfigurations` | `${ApiConstants.SQL_POOL_CONFIG_PATH}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/PoolConfigResource.java:73` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:11` |
| `GET` | `/v1/pools/{id}` | `PoolConfigResource#getPoolConfig` | `${ApiConstants.SQL_POOL_CONFIG_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/PoolConfigResource.java:119` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:11` |
| `PATCH` | `/v1/pools/{id}` | `PoolConfigResource#updatePoolConfig` | `${ApiConstants.SQL_POOL_CONFIG_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/PoolConfigResource.java:174` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:11` |
| `GET` | `/v1/reservations` | `ReservationResource#getReservations` | `${ApiConstants.SQL_POOL_RESERVATION_PATH}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ReservationResource.java:71` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:7` |
| `POST` | `/v1/reservations` | `ReservationResource#makeReservations` | `${ApiConstants.SQL_POOL_RESERVATION_PATH}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ReservationResource.java:180` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:7` |
| `GET` | `/v1/reservations/{id}` | `ReservationResource#findReservation` | `${ApiConstants.SQL_POOL_RESERVATION_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ReservationResource.java:139` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:7` |
| `PATCH` | `/v1/reservations/{id}` | `ReservationResource#updateReservation` | `${ApiConstants.SQL_POOL_RESERVATION_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ReservationResource.java:224` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:7` |
| `DELETE` | `/v1/reservations/{reservation_id}` | `ReservationResource#deleteReservation` | `${ApiConstants.SQL_POOL_RESERVATION_PATH}/{reservation_id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ReservationResource.java:269` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:7` |
| `GET` | `/v1/servers` | `ServerResource#getAvailableServers` | `${ApiConstants.SQL_POOL_SERVER_PATH}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ServerResource.java:71` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:10` |
| `POST` | `/v1/servers` | `ServerResource#register` | `${ApiConstants.SQL_POOL_SERVER_PATH}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ServerResource.java:173` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:10` |
| `DELETE` | `/v1/servers/{id}` | `ServerResource#unRegister` | `${ApiConstants.SQL_POOL_SERVER_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ServerResource.java:263` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:10` |
| `GET` | `/v1/servers/{id}` | `ServerResource#getServer` | `${ApiConstants.SQL_POOL_SERVER_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ServerResource.java:127` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:10` |
| `PATCH` | `/v1/servers/{id}` | `ServerResource#updateServer` | `${ApiConstants.SQL_POOL_SERVER_PATH}/{id}` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ServerResource.java:217` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:10` |
| `GET` | `/v1/servers/{id}/logs` | `ServerResource#getServerStatusLogs` | `${ApiConstants.SQL_POOL_SERVER_PATH}/{id}/logs` | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ServerResource.java:295` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:10` |
| `GET` | `/{bundleId}` | `ExposureBundlesResource#getExposureBundle` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:685` |
| `GET` | `/{bundleId}/metrics` | `ExposureBundlesResource#getExposureBundleMetrics` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:847` |
| `POST` | `/{bundleId}/tableset` | `ExposureBundlesResource#createExposureBundleTableSet` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:255` |
| `GET` | `/{bundleId}/tablesets` | `ExposureBundlesResource#getExposureBundleTableSets` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:763` |
| `GET` | `/{jobId}` | `VariationJobsResource#getJob` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:263` |
| `PATCH` | `/{jobId}` | `VariationJobsResource#updateJob` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:313` |
| `DELETE` | `/{variationId}` | `ExposureVariationsResource#deleteExposureVariationByVariationId` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureVariationsResource.java:218` |
| `GET` | `/{variationId}` | `ExposureVariationsResource#getExposureVariation` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureVariationsResource.java:166` |
| `GET` | `[controller]/entity-names` | `AdminController#GetEntityNames` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.cs:60` |
| `POST` | `[controller]/normalized-migration/{tenantId}` | `AdminController#StartNormalizedMigrationAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.cs:27` |
| `GET` | `[controller]/tenants` | `AdminController#GetTenants` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.cs:51` |
| `GET` | `[controller]/{entityName}` | `SchemaController#GetSchemaAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/SchemaController.cs:29` |
| `DELETE` | `[controller]/{tenantId}` | `TenantController#DeprovisionTenantAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/TenantController.cs:77` |
| `GET` | `[controller]/{tenantId}` | `TenantController#GetProvisioningStatusAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/TenantController.cs:31` |
| `POST` | `[controller]/{tenantId}` | `TenantController#ProvisionTenantAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/TenantController.cs:52` |
| `POST` | `[controller]/{tenantId}/db/maintain` | `TenantController#MaintainTenantDbAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/TenantController.cs:97` |
| `DELETE` | `aws/snapshots` | `AdminController#DeleteSnapShots` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Aws.cs:97` |
| `GET` | `aws/snapshots` | `AdminController#ListSnapShots` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Aws.cs:77` |
| `POST` | `aws/snapshots/tags` | `AdminController#UpsertSnapshotsTags` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Aws.cs:117` |
| `DELETE` | `aws/volumes` | `AdminController#DeleteVolumes` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Aws.cs:36` |
| `GET` | `aws/volumes` | `AdminController#ListVolumes` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Aws.cs:15` |
| `POST` | `aws/volumes/tags` | `AdminController#UpsertVolumesTags` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Aws.cs:56` |
| `POST` | `background-jobs/{jobName}` | `AdminController#SubmitBackgroundJob` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Job.cs:44` |
| `POST` | `clusters/{clusterName}/instances/{instanceName}/database-snapshots` | `AdminController#CreateOnDemandSnapshotDatabase` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SnapshotDatabase.cs:12` |
| `GET` | `clusters/{tenantId}/namespaces/{ns}/sql-instances/invalid` | `AdminController#ListInvalidSqlInstancesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:139` |
| `GET` | `databases` | `AdminDataController#GetDatabasesAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:80` |
| `DELETE` | `databases/{databaseId}` | `AdminDataController#DeleteDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:279` |
| `POST` | `databases/{databaseId}/archive` | `AdminDataController#ArchiveDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:337` |
| `POST` | `databases/{databaseId}/move` | `AdminDataController#MoveDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:406` |
| `POST` | `databases/{databaseId}/reindex` | `AdminDataController#ReindexDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:179` |
| `POST` | `databases/{databaseId}/shrink` | `AdminDataController#ShrinkDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:122` |
| `POST` | `databases/{databaseId}/statistics/update` | `AdminDataController#UpdateDatabaseStatisticsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:229` |
| `GET` | `databases/{databaseRiId}` | `AdminDataController#GetDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.Databases.cs:39` |
| `DELETE` | `enterprise/v1/provision/tenant/{tenantId}` | `EnterpriseTenantController#RemoveEnterpriseSettingAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EnterpriseTenantController.cs:89` |
| `GET` | `enterprise/v1/provision/tenant/{tenantId}` | `EnterpriseTenantController#GetEnterpriseSettingStatusAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EnterpriseTenantController.cs:32` |
| `POST` | `enterprise/v1/provision/tenant/{tenantId}` | `EnterpriseTenantController#AddEnterpriseSettingAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EnterpriseTenantController.cs:60` |
| `GET` | `enterprise/v1/tenants/{tenantId}/settings` | `EnterpriseTenantController#GetEnterpriseSettings` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EnterpriseTenantController.cs:116` |
| `PUT` | `enterprise/v1/tenants/{tenantId}/settings` | `EnterpriseTenantController#PutEnterpriseSettings` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EnterpriseTenantController.cs:143` |
| `ANY` | `internal/v1/[controller]` | `AdminController` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.cs:15` |
| `GET` | `internal/v1/[controller]/dependency-health` | `HealthController#GetDependencyHealth` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/HealthController.cs:13` |
| `GET` | `internal/v1/[controller]/dependency-health` | `HealthController#GetDependencyHealth` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/HealthController.cs:13` |
| `GET` | `internal/v1/[controller]/keys` | `CacheController#ListKeysAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/CacheController.cs:70` |
| `DELETE` | `internal/v1/[controller]/keys/{**key}` | `CacheController#DeleteKeyAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/CacheController.cs:110` |
| `GET` | `internal/v1/[controller]/keys/{**key}` | `CacheController#GetKeyAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/CacheController.cs:34` |
| `POST` | `internal/v1/[controller]/report` | `JobMetricsController#ReportAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/Internal/v1/JobMetricsController.cs:30` |
| `POST` | `internal/v1/[controller]/report` | `JobMetricsController#ReportAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/JobMetricsController.cs:30` |
| `POST` | `internal/v1/integration-test` | `IntegrationTestController#RunTestsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/IntegrationTestController.cs:76` |
| `GET` | `internal/v1/integration-test/results` | `IntegrationTestController#GetTestResultsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/IntegrationTestController.cs:126` |
| `DELETE` | `internal/v1/{tenantId}/edm/edm-record/{riGuid}` | `EdmController#DeleteEdmRecordAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/EdmController.cs:39` |
| `PATCH` | `internal/v1/{tenantId}/edm/edm-record/{riGuid}` | `EdmController#UpdateEdmRecordAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/EdmController.cs:59` |
| `DELETE` | `internal/v1/{tenantId}/sqlInstances/{serverName}/databases/{databaseName}/invalidate-connection-string` | `SqlInstancesController#InvalidateConnectionString` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/SqlInstancesController.cs:33` |
| `GET` | `internal/variation/v1/exposurevariations` | `InternalVariationResource#getExposureVariations` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:196` |
| `GET` | `internal/variation/v1/exposurevariations/admin` | `InternalVariationResource#getExposureVariationsAsAdmin` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:281` |
| `GET` | `internal/variation/v1/exposurevariations/{variationId}` | `InternalVariationResource#getExposureVariation` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:55` |
| `GET` | `internal/variation/v1/exposurevariations/{variationId}/admin` | `InternalVariationResource#getExposureVariationAsAdmin` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:129` |
| `GET` | `job-reservations` | `AdminController#GetJobReservationsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobReservations.cs:18` |
| `POST` | `job-reservations` | `AdminController#CreateJobReservationAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobReservations.cs:95` |
| `GET` | `job-reservations/tenants/{tenantId}/sql-instances/{instanceName}/job-types/{jobName}/job-reservations` | `AdminController#GetJobReservationsByTenantAndInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobReservations.cs:177` |
| `DELETE` | `job-reservations/{jobId}` | `AdminController#DeleteJobReservationByJobIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobReservations.cs:63` |
| `GET` | `job-reservations/{reservationId}` | `AdminController#GetJobReservationByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobReservations.cs:39` |
| `PUT` | `job-reservations/{reservationId}` | `AdminController#UpdateJobReservationAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobReservations.cs:151` |
| `GET` | `job-types` | `AdminController#GetJobTypesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobType.cs:16` |
| `POST` | `job-types` | `AdminController#AddJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobType.cs:66` |
| `GET` | `job-types-limits` | `AdminController#GetAllJobTypeLimitsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:207` |
| `POST` | `job-types-limits` | `AdminController#AddJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:16` |
| `POST` | `job-types-limits/seed` | `AdminController#SeedJobTypeLimitsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:253` |
| `GET` | `job-types-limits/tenants/{tenantId}` | `AdminController#GetAllJobTypeLimitsByTenantAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:181` |
| `GET` | `job-types-limits/tenants/{tenantId}/instances/{instanceName}` | `AdminController#GetAllJobTypeLimitsByInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:135` |
| `DELETE` | `job-types-limits/tenants/{tenantId}/instances/{instanceName}/job-names/{jobTypeName}` | `AdminController#DeleteJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:46` |
| `GET` | `job-types-limits/tenants/{tenantId}/instances/{instanceName}/job-names/{jobTypeName}` | `AdminController#GetJobTypeLimitAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:107` |
| `PUT` | `job-types-limits/tenants/{tenantId}/instances/{instanceName}/job-names/{jobTypeName}` | `AdminController#UpdateJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:73` |
| `GET` | `job-types-limits/tenants/{tenantId}/job-names/{jobTypeName}` | `AdminController#GetAllJobTypeLimitsByJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:154` |
| `GET` | `job-types-limits/{id}` | `AdminController#GetJobTypeLimitByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobTypeLimit.cs:229` |
| `DELETE` | `job-types/{id}` | `AdminController#DeleteJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobType.cs:148` |
| `GET` | `job-types/{id}` | `AdminController#GetJobTypeByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobType.cs:36` |
| `PUT` | `job-types/{id}` | `AdminController#UpdateJobTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobType.cs:100` |
| `DELETE` | `jobs/{jobId}` | `AdminController#CancelJobAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Jobs.cs:40` |
| `GET` | `jobs/{jobId}` | `AdminController#GetJobDetailsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Jobs.cs:17` |
| `POST` | `kms-infos/tenant/{tenantId}` | `AdminController#UpdateKmsKeyForTenantAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:144` |
| `GET` | `locks` | `AdminController#GetLockInfoAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.system.cs:15` |
| `DELETE` | `locks/release/{sessionId}` | `AdminController#ReleaseLockAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.system.cs:36` |
| `GET` | `maintenance/configs` | `AdminController#ListConfigsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:23` |
| `POST` | `maintenance/configs` | `AdminController#CreateConfigAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:107` |
| `GET` | `maintenance/configs/type/{scheduleType}` | `AdminController#GetConfigsByTypeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:48` |
| `DELETE` | `maintenance/configs/{configId}` | `AdminController#DeleteConfigAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:224` |
| `GET` | `maintenance/configs/{configId}` | `AdminController#GetConfigAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:74` |
| `POST` | `maintenance/configs/{configId}/activate` | `AdminController#ActivateConfigAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:149` |
| `POST` | `maintenance/configs/{configId}/deactivate` | `AdminController#DeactivateConfigAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:188` |
| `GET` | `maintenance/configs/{configId}/schedules` | `AdminController#GetSchedulesByConfigIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:260` |
| `GET` | `maintenance/db-count` | `AdminController#GetDatabaseCountsGroupedAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:450` |
| `GET` | `maintenance/schedules` | `AdminController#ListSchedulesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:286` |
| `PATCH` | `maintenance/schedules/bulk` | `AdminController#BulkUpdateSchedulesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:377` |
| `POST` | `maintenance/schedules/{scheduleId:int}/trigger` | `AdminController#TriggerScheduleUpgradeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:509` |
| `GET` | `maintenance/schedules/{scheduleId}` | `AdminController#GetScheduleAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:577` |
| `GET` | `maintenance/sql-images` | `AdminController#GetAvailableSqlImagesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:426` |
| `GET` | `maintenance/tenants/{tenantId}/schedules` | `AdminController#GetSchedulesByTenantIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:320` |
| `GET` | `meta/clusters` | `AdminController#ListClusterDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Cluster.cs:17` |
| `POST` | `meta/clusters` | `AdminController#CreateClusterAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Cluster.cs:57` |
| `DELETE` | `meta/clusters/{clusterName}` | `AdminController#DeleteClusterAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Cluster.cs:115` |
| `GET` | `meta/clusters/{clusterName}` | `AdminController#GetClusterByNameAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Cluster.cs:37` |
| `PUT` | `meta/clusters/{clusterName}` | `AdminController#UpdateClusterAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Cluster.cs:89` |
| `GET` | `meta/connection-strings` | `AdminController#ListConnectionStringDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.ConnectionString.cs:16` |
| `GET` | `meta/connection-strings/{externalId}` | `AdminController#GetConnectionStringByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.ConnectionString.cs:36` |
| `PUT` | `meta/connection-strings/{externalId}` | `AdminController#UpdateConnectionStringAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.ConnectionString.cs:56` |
| `GET` | `meta/data-vaults` | `AdminController#ListDataVaultMetadatasAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.DataVaultSettings.cs:18` |
| `POST` | `meta/data-vaults` | `AdminController#CreateDataVaultMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.DataVaultSettings.cs:58` |
| `DELETE` | `meta/data-vaults/{tenantId}` | `AdminController#DeleteDataVaultMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.DataVaultSettings.cs:103` |
| `GET` | `meta/data-vaults/{tenantId}` | `AdminController#GetDataVaultMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.DataVaultSettings.cs:37` |
| `PATCH` | `meta/data-vaults/{tenantId}` | `AdminController#UpdateDataVaultMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.DataVaultSettings.cs:79` |
| `GET` | `meta/databases` | `AdminController#ListDatabasesDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Database.cs:20` |
| `GET` | `meta/jobs` | `AdminController#ListJobsDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobMeta.cs:16` |
| `POST` | `meta/jobs` | `AdminController#CreateJobAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobMeta.cs:81` |
| `DELETE` | `meta/jobs/{externalJobId}` | `AdminController#DeleteJobAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobMeta.cs:144` |
| `GET` | `meta/jobs/{externalJobId}` | `AdminController#GetJobByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobMeta.cs:61` |
| `PUT` | `meta/jobs/{externalJobId}` | `AdminController#UpdateJobAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.JobMeta.cs:118` |
| `GET` | `meta/kms-infos` | `AdminController#ListKmsInfosAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:19` |
| `POST` | `meta/kms-infos` | `AdminController#CreateKmsInfoAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:77` |
| `GET` | `meta/kms-infos/tenant/{tenantId}` | `AdminController#GetKmsInfosByTenantAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:38` |
| `DELETE` | `meta/kms-infos/{id}` | `AdminController#DeleteKmsInfoAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:121` |
| `GET` | `meta/kms-infos/{id}` | `AdminController#GetKmsInfoAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:58` |
| `PATCH` | `meta/kms-infos/{id}` | `AdminController#UpdateKmsInfoAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.KmsInfos.cs:98` |
| `GET` | `meta/logins` | `AdminController#ListLoginsDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Login.cs:16` |
| `POST` | `meta/logins` | `AdminController#CreateLogin` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Login.cs:56` |
| `DELETE` | `meta/logins/database/{databaseId}/login/{loginName}` | `AdminController#DeleteLoginAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Login.cs:127` |
| `GET` | `meta/logins/database/{databaseId}/login/{loginName}` | `AdminController#GetLoginByDatabaseIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Login.cs:36` |
| `PUT` | `meta/logins/database/{databaseId}/login/{loginName}` | `AdminController#UpdateLoginAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Login.cs:101` |
| `GET` | `meta/sql-instances` | `AdminController#ListSqlIntanceDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:19` |
| `POST` | `meta/sql-instances` | `AdminController#CreateSqlInstance` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:59` |
| `PUT` | `meta/sql-instances/{instanceName}` | `AdminController#UpdateSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:91` |
| `GET` | `meta/tenants` | `AdminController#ListTenantDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Tenant.cs:18` |
| `GET` | `meta/tenants` | `AdminController#ListTenantsMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Tenants.cs:18` |
| `POST` | `meta/tenants` | `AdminController#CreateTenantAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Tenant.cs:58` |
| `POST` | `meta/tenants` | `AdminController#CreateTenantMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Tenants.cs:58` |
| `POST` | `meta/tenants/sync-database-cards` | `AdminController#SyncDatabaseCardsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Tenant.cs:143` |
| `DELETE` | `meta/tenants/{tenantId}` | `AdminController#DeleteTenantMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Tenants.cs:105` |
| `GET` | `meta/tenants/{tenantId}` | `AdminController#GetTenantByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Tenant.cs:38` |
| `GET` | `meta/tenants/{tenantId}` | `AdminController#GetTenantMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Tenants.cs:37` |
| `PATCH` | `meta/tenants/{tenantId}` | `AdminController#UpdateTenantMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Tenants.cs:80` |
| `PUT` | `meta/tenants/{tenantId}` | `AdminController#UpdateTenantAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Tenant.cs:90` |
| `GET` | `meta/tenants/{tenantId}/edms` | `AdminController#ListEdmsMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Edms.cs:17` |
| `POST` | `meta/tenants/{tenantId}/edms` | `AdminController#CreateEdmMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Edms.cs:59` |
| `DELETE` | `meta/tenants/{tenantId}/edms/{riGuid}` | `AdminController#DeleteEdmMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Edms.cs:110` |
| `GET` | `meta/tenants/{tenantId}/edms/{riGuid}` | `AdminController#GetEdmMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Edms.cs:37` |
| `PATCH` | `meta/tenants/{tenantId}/edms/{riGuid}` | `AdminController#UpdateEdmMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Edms.cs:82` |
| `GET` | `meta/tenants/{tenantId}/transient-dbs` | `AdminController#ListTransientDbsMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.TransientDbs.cs:18` |
| `POST` | `meta/tenants/{tenantId}/transient-dbs` | `AdminController#CreateTransientDbMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.TransientDbs.cs:60` |
| `DELETE` | `meta/tenants/{tenantId}/transient-dbs/{riGuid}` | `AdminController#DeleteTransientDbMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.TransientDbs.cs:111` |
| `GET` | `meta/tenants/{tenantId}/transient-dbs/{riGuid}` | `AdminController#GetTransientDbMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.TransientDbs.cs:38` |
| `PATCH` | `meta/tenants/{tenantId}/transient-dbs/{riGuid}` | `AdminController#UpdateTransientDbMetadataAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.TransientDbs.cs:83` |
| `DELETE` | `meta/{tenantId}/sql-instances/{instanceName}` | `AdminController#DeleteSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:117` |
| `GET` | `meta/{tenantId}/sql-instances/{instanceName}` | `AdminController#GetSqlInstanceByNameAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:39` |
| `POST` | `meta/{tenantId}/sql-instances/{instanceName}/databases` | `AdminController#CreateDatabase` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Database.cs:62` |
| `DELETE` | `meta/{tenantId}/sql-instances/{instanceName}/databases/{databaseName}` | `AdminController#DeleteDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Database.cs:139` |
| `GET` | `meta/{tenantId}/sql-instances/{instanceName}/databases/{databaseName}` | `AdminController#GetDatabaseByNameAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Database.cs:41` |
| `PUT` | `meta/{tenantId}/sql-instances/{instanceName}/databases/{databaseName}` | `AdminController#UpdateDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Database.cs:112` |
| `POST` | `meta/{tenantId}/sql-instances/{instanceName}/databases/{databaseName}/shrink` | `AdminController#ShrinkDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Database.cs:160` |
| `POST` | `meta/{tenantId}/sql-instances/{instanceName}/shrink-databases` | `AdminController#ShrinkInstanceDatabasesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstance.cs:165` |
| `GET` | `migrate/get-snapshots` | `MigrateDataController#GetManagedSqlInstanceSnapshotsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateDataController.cs:184` |
| `GET` | `migrate/get-snapshots-internal` | `MigrateInternalDataController#GetManagedSqlInstanceSnapshotsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateInternalDataController.cs:184` |
| `POST` | `migrate/recreate-from-snapshot` | `MigrateDataController#GetManagedSqlInstanceSnapshotsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateDataController.cs:228` |
| `POST` | `migrate/recreate-from-snapshot-internal` | `MigrateInternalDataController#GetManagedSqlInstanceSnapshotsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateInternalDataController.cs:228` |
| `POST` | `migrate/restart-sql-instance` | `MigrateDataController#ForceRestartSqlInstanceAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateDataController.cs:140` |
| `POST` | `migrate/restart-sql-instance-internal` | `MigrateInternalDataController#ForceRestartSqlInstanceAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateInternalDataController.cs:140` |
| `POST` | `migrate/sql-instance` | `MigrateDataController#ForceMigrateSqlInstanceToClusterAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateDataController.cs:44` |
| `POST` | `migrate/sql-instance-internal` | `MigrateInternalDataController#ForceMigrateSqlInstanceToClusterAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateInternalDataController.cs:44` |
| `POST` | `migrate/start-edm-populate-job` | `MigrateDataController#StartBackgroundJob` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateDataController.cs:291` |
| `POST` | `migrate/start-edm-populate-job-internal` | `MigrateInternalDataController#StartBackgroundJob` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateInternalDataController.cs:291` |
| `POST` | `migrate/upgrade-sql-instance` | `MigrateDataController#ForceUpgradeSqlInstanceAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateDataController.cs:96` |
| `POST` | `migrate/upgrade-sql-instance-internal` | `MigrateInternalDataController#ForceUpgradeSqlInstanceToClusterAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MigrateInternalDataController.cs:96` |
| `GET` | `patch-ops/admin` | `CardController#GetPatchOpsAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Patch.cs:57` |
| `DELETE` | `provision/tenant/{tenantId}` | `TenantsController#DeprovisionTenantAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/TenantsController.cs:65` |
| `GET` | `provision/tenant/{tenantId}` | `TenantsController#GetTenantProvisioningStatusAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/TenantsController.cs:44` |
| `POST` | `provision/tenant/{tenantId}` | `TenantsController#ProvisionTenantAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/TenantsController.cs:23` |
| `PATCH` | `provision/tenant/{tenantId}/enterprise-upgrade` | `TenantsController#PerformEnterpriseUpgradeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/TenantsController.cs:86` |
| `POST` | `recurring-jobs/{jobName}` | `AdminController#SubmitRecurringJob` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Job.cs:17` |
| `POST` | `recurring-jobs/{jobName}` | `AdminController#SubmitRecurringJobAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Jobs.cs:60` |
| `DELETE` | `snapshots/cleanup` | `AdminController#CleanupSnapshots` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/Internal/v1/AdminController.Snapshots.cs:15` |
| `GET` | `tenant/{tenantId}/instance/{instanceName}/databases/count` | `AdminController#GetDatabaseCountForSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Maintenance.cs:475` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/data-volume-throughput` | `AdminController#GetDataVolumeThroughputStateAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstanceVolumes.cs:92` |
| `POST` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/data-volume-throughput` | `AdminController#UpdateDataVolumeThroughputAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.SqlInstanceVolumes.cs:27` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/describe` | `AdminController#GetDescribeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:112` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/events` | `AdminController#GetInstanceEventsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:143` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/logs` | `AdminController#GetInstanceLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:277` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/resource-usage` | `AdminController#GetInstanceResourceUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:174` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/pod/{podName}/logs` | `AdminController#GetPodLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:204` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/pod/{podName}/logs/previous` | `AdminController#GetPreviousPodLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:242` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespace/{ns}/pods` | `AdminController#GetPodsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:89` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/namespaces` | `AdminController#GetNamespacesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:43` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/node/{nodeName}/describe` | `AdminController#DescribeNodeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:66` |
| `GET` | `tenant/{tenant}/cluster/{cluster}/nodes` | `AdminController#GetNodesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Kubernetes.cs:20` |
| `GET` | `tenant/{tenant}/sql-instances/{instance}/server-log` | `AdminController#GetServerLogAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:199` |
| `GET` | `tenant/{tenant}/sql-instances/{instance}/tempdb-session-usage` | `AdminController#GetTempDbSessionUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:269` |
| `PATCH` | `tenant/{tenant}/sql-instances/{instance}/tempdb-shrink` | `AdminController#ShrinkTempDbAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:307` |
| `GET` | `tenant/{tenant}/sql-instances/{instance}/tempdb-usage` | `AdminController#GetTempDbUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:232` |
| `DELETE` | `tenants/{tenantId}` | `AdminController#DeleteTenantAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Tenant.cs:116` |
| `POST` | `tenants/{tenant}/sql-instances/{instance}/Databases/system` | `AdminController#AttachDatabase` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:86` |
| `DELETE` | `tenants/{tenant}/sql-instances/{instance}/Databases/{databaseName}/system` | `AdminController#DetachOrDropDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:161` |
| `PATCH` | `tenants/{tenant}/sql-instances/{instance}/Databases/{databaseName}/system` | `AdminController#OffLineOnlineDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:123` |
| `GET` | `tenants/{tenant}/sql-instances/{instance}/databases/system` | `AdminController#GetDatabasesWithMdfLdf` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:54` |
| `GET` | `tenants/{tenant}/sql-instances/{instance}/databases/{databaseName}/system` | `AdminController#GetDatabaseWithMdfLdf` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.Sys.cs:21` |
| `DELETE` | `v1/[controller]/all/all` | `JobsController#CancelJobAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/JobsController.cs:95` |
| `POST` | `v1/[controller]/databridge/notify` | `NotificationController#ProcessDataBridgeNotificationAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/NotificationController.cs:28` |
| `GET` | `v1/[controller]/dependency-health` | `HealthController#GetDependencyHealth` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HealthController.cs:13` |
| `GET` | `v1/[controller]/instances` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:146` |
| `GET` | `v1/[controller]/internal/securables/s2s/{tenantId}` | `AdminDataController#GetSecurableS2S` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:164` |
| `DELETE` | `v1/[controller]/internal/securables/s2s/{tenantId}/{securableId}` | `AdminDataController#DeleteSecurableS2SAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:261` |
| `GET` | `v1/[controller]/internal/securables/s2s/{tenantId}/{securableId}` | `AdminDataController#GetSecurableAsyncS2S` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:200` |
| `PATCH` | `v1/[controller]/internal/securables/s2s/{tenantId}/{securableId}` | `AdminDataController#PatchSecurableAsyncS2S` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:233` |
| `POST` | `v1/[controller]/internal/securables/s2s/{tenantId}/{securableId}/archive` | `AdminDataController#ArchiveSecurableS2SAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:299` |
| `GET` | `v1/[controller]/jobs` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:623` |
| `DELETE` | `v1/[controller]/jobs/{jobId}` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:657` |
| `GET` | `v1/[controller]/jobs/{jobId}` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:680` |
| `POST` | `v1/[controller]/leases` | `OnDemandController#ReserveLeaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:29` |
| `DELETE` | `v1/[controller]/leases/{leaseId:guid}` | `OnDemandController#DeleteTransientDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:228` |
| `GET` | `v1/[controller]/leases/{leaseId:guid}` | `OnDemandController#GetLeaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:63` |
| `POST` | `v1/[controller]/leases/{leaseId:guid}/attach` | `OnDemandController#AttachTransientDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:167` |
| `POST` | `v1/[controller]/leases/{leaseId:guid}/create` | `OnDemandController#CreateTransientDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:116` |
| `GET` | `v1/[controller]/leases/{leaseId:guid}/details` | `OnDemandController#GetLeaseDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:92` |
| `POST` | `v1/[controller]/leases/{leaseId:guid}/export` | `OnDemandController#ExportTransientDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:197` |
| `POST` | `v1/[controller]/leases/{leaseId:guid}/import` | `OnDemandController#ImportTransientDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/OnDemandController.cs:139` |
| `GET` | `v1/[controller]/paths` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:701` |
| `GET` | `v1/[controller]/securables` | `AdminDataController#GetSecurable` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:92` |
| `DELETE` | `v1/[controller]/securables/{securableId}` | `AdminDataController#DeleteSecurableAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:375` |
| `GET` | `v1/[controller]/securables/{securableId}` | `AdminDataController#GetSecurableAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:69` |
| `PATCH` | `v1/[controller]/securables/{securableId}` | `AdminDataController#PatchSecurableAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:130` |
| `POST` | `v1/[controller]/securables/{securableId}/archive` | `AdminDataController#ArchiveSecurableAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:342` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:170` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/app-locks` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:750` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/blocking-sessions` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:504` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/configurations` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:722` |
| `POST` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/check-db` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:441` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/databases` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:198` |
| `DELETE` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:317` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:283` |
| `POST` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:351` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:249` |
| `POST` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/restart` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:410` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/sessions` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:475` |
| `DELETE` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/sessions/{sessionId}` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:570` |
| `POST` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/upgrade` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:379` |
| `GET` | `v1/[controller]/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/values` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:600` |
| `GET` | `v1/[controller]/tenants` | `AdminController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.cs:121` |
| `DELETE` | `v1/[controller]/{jobId}` | `JobsController#CancelJobAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/JobsController.cs:69` |
| `GET` | `v1/[controller]/{jobId}` | `JobsController#GetJobStateAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/JobsController.cs:33` |
| `GET` | `v1/[controller]/{jobId}` | `JobsController#GetJobStateAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/JobsController.cs:32` |
| `GET` | `v1/[controller]/{jobId}` | `ManagedSqlInternalJobsController#GetJobStateAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ManagedSqlInternalJobsController.cs:38` |
| `GET` | `v1/[controller]/{jobId}` | `ManagedSqlJobsController#GetJobStateAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ManagedSqlJobsController.cs:38` |
| `GET` | `v1/[controller]/{jobId}/details` | `JobsController#GetJobDetailsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/JobsController.cs:47` |
| `GET` | `v1/[controller]/{jobId}/details` | `JobsController#GetJobDetailsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/JobsController.cs:51` |
| `GET` | `v1/[controller]/{jobId}/details` | `ManagedSqlInternalJobsController#GetJobDetailsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ManagedSqlInternalJobsController.cs:57` |
| `GET` | `v1/[controller]/{jobId}/details` | `ManagedSqlJobsController#GetJobDetailsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ManagedSqlJobsController.cs:57` |
| `GET` | `v1/catalog/[controller]/{entityName}` | `SchemaController#GetSchemaAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/SchemaController.cs:28` |
| `POST` | `v1/helm/cluster/{cluster}/namespace/{ns}/release/{release}/install` | `HelmController#InstallReleaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:102` |
| `POST` | `v1/helm/cluster/{cluster}/namespace/{ns}/release/{release}/uninstall` | `HelmController#UninstallReleaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:151` |
| `POST` | `v1/helm/cluster/{cluster}/namespace/{ns}/release/{release}/upgrade` | `HelmController#UpgradeReleaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:126` |
| `GET` | `v1/helm/cluster/{cluster}/namespace/{ns}/release/{release}/values` | `HelmController#GetValuesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:78` |
| `POST` | `v1/helm/cluster/{cluster}/namespace/{ns}/release/{release}/values` | `HelmController#GetValuesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:79` |
| `GET` | `v1/helm/cluster/{cluster}/namespace/{ns}/releases` | `HelmController#ListReleasesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:30` |
| `POST` | `v1/helm/cluster/{cluster}/namespace/{ns}/releases` | `HelmController#ListReleasesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:31` |
| `GET` | `v1/helm/cluster/{cluster}/releases` | `HelmController#ListReleasesInAllNamespacesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:54` |
| `POST` | `v1/helm/cluster/{cluster}/releases` | `HelmController#ListReleasesInAllNamespacesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/HelmController.cs:55` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/check-aws-cli-prerequisites` | `InstanceOperationsController#CheckAwsCliPrerequisitesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:659` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/configure-aws-cli-s3` | `InstanceOperationsController#ConfigureAwsCliForS3Async` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:687` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/copy-from-instance` | `InstanceOperationsController#CopyFromInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:369` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/copy-to-instance` | `InstanceOperationsController#CopyToInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:342` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/backup` | `InstanceOperationsController#BackupDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:516` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/list-mdf-ldf-paths` | `InstanceOperationsController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:546` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/mdf-ldf-paths` | `InstanceOperationsController` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:545` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/mdf-ldf-paths` | `InstanceOperationsController#GetMdfFilePathsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:573` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/mdf-path` | `InstanceOperationsController#GetMdfFilePathsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:601` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/mdf-path` | `InstanceOperationsController#GetMdfFilePathsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:602` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/database/{database}/restore` | `InstanceOperationsController#RestoreDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:487` |
| `DELETE` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/directory` | `InstanceOperationsController#RemoveDirectoryOnInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:315` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/directory` | `InstanceOperationsController#MakeDirectoryOnInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:288` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/extract-dacpac` | `InstanceOperationsController#ExtractDacpacAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:424` |
| `DELETE` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file` | `InstanceOperationsController#DeleteFileAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:121` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file` | `InstanceOperationsController#ReadFileAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:92` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file` | `InstanceOperationsController#WriteFileAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:149` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file-exists` | `InstanceOperationsController#FileExistsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:63` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file-exists` | `InstanceOperationsController#FileExistsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:64` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file/chunk/download` | `InstanceOperationsController#DownloadFileChunkAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:261` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file/chunk/upload` | `InstanceOperationsController#UploadFileChunkAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:233` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file/modified-date` | `InstanceOperationsController#GetFileModifiedDateAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:204` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file/modified-date` | `InstanceOperationsController#GetFileModifiedDateAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:205` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file/size` | `InstanceOperationsController#GetFileSizeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:175` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/file/size` | `InstanceOperationsController#GetFileSizeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:176` |
| `DELETE` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files` | `InstanceOperationsController#DeleteFilesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:746` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files` | `InstanceOperationsController#ListFilesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:33` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files` | `InstanceOperationsController#ListFilesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:34` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files-or-create-directory` | `InstanceOperationsController#ListFilesOrCreateDirectoryAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:396` |
| `GET` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files-with-modified-date` | `InstanceOperationsController#ListFilesWithModifiedDateAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:775` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/files-with-modified-date` | `InstanceOperationsController#ListFilesWithModifiedDateAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:776` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/import-dacpac` | `InstanceOperationsController#ImportDacpacAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:452` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/read-file` | `InstanceOperationsController#ReadFileAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:93` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/search-running-processes` | `InstanceOperationsController#SearchRunningProcessesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:807` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/storage-usage` | `InstanceOperationsController#GetStorageUsageInPathAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:631` |
| `POST` | `v1/instance-operations/tenant/{tenant}/cluster/{cluster}/namespace/{ns}/instance/{instance}/upload-to-s3-aws-cli` | `InstanceOperationsController#UploadFileToS3ViaAwsCliAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/InstanceOperationsController.cs:714` |
| `DELETE` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}` | `KubernetesController#DeleteNamespaceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:477` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/copy-from` | `KubernetesController#CopyFromAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:552` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/copy-to` | `KubernetesController#CopyToAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:524` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/events` | `KubernetesController#GetEventsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:427` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/events` | `KubernetesController#GetEventsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:428` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/describe` | `KubernetesController#DescribePodAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:385` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/describe` | `KubernetesController#DescribePodAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:386` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/diskusage` | `KubernetesController#GetDiskUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:337` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/diskusage` | `KubernetesController#GetDiskUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:338` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/events` | `KubernetesController#GetInstanceEventsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:365` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/events` | `KubernetesController#GetInstanceEventsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:366` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/logs` | `KubernetesController#GetInstanceLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:417` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/logs` | `KubernetesController#GetInstanceLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:418` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/resource-usage` | `KubernetesController#GetResourceUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:375` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/instance/{instance}/resource-usage` | `KubernetesController#GetResourceUsageAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:376` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/persistentvolume/{name}` | `KubernetesController#GetPersistentVolumeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:208` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/persistentvolume/{name}` | `KubernetesController#GetPersistentVolumeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:209` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/persistentvolumeclaim/{name}` | `KubernetesController#GetPersistentVolumeClaimAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:182` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/persistentvolumeclaim/{name}` | `KubernetesController#GetPersistentVolumeClaimAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:183` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/pod/{name}` | `KubernetesController#GetPodAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:234` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/pod/{name}` | `KubernetesController#GetPodAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:235` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/secret/{name}` | `KubernetesController#GetSecretAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:260` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/secret/{name}` | `KubernetesController#GetSecretAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:261` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/service/{name}` | `KubernetesController#GetServiceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:312` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/service/{name}` | `KubernetesController#GetServiceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:313` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/statefulset/{name}` | `KubernetesController#GetStatefulSetAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:286` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/statefulset/{name}` | `KubernetesController#GetStatefulSetAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:287` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/{objectType}` | `KubernetesController#GetPersistentVolumeClaimAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:157` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/{objectType}` | `KubernetesController#GetPersistentVolumeClaimAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:158` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/{objectType}/{objectName}` | `KubernetesController#GetItemAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:131` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/object/{objectType}/{objectName}` | `KubernetesController#GetItemAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:132` |
| `DELETE` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pod/{pod}` | `KubernetesController#DeletePodAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:500` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pod/{pod}/format-volume` | `KubernetesController#FormatVolumeAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:629` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pod/{pod}/logs` | `KubernetesController#GetPodLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:395` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pod/{pod}/logs` | `KubernetesController#GetPodLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:396` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pod/{pod}/logs/previous` | `KubernetesController#GetPreviousPodLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:407` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pod/{pod}/logs/previous` | `KubernetesController#GetPreviousPodLogsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:408` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pods` | `KubernetesController#GetPodsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:452` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/pods` | `KubernetesController#GetPodsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:453` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/reconcile-service-annotations` | `KubernetesController#ReconcileServiceAnnotationsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:580` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespace/{ns}/scale-stateful-set` | `KubernetesController#ScaleStatefulSetAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:605` |
| `GET` | `v1/kubernetes/cluster/{cluster}/namespaces` | `KubernetesController#GetNamespacesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:82` |
| `POST` | `v1/kubernetes/cluster/{cluster}/namespaces` | `KubernetesController#GetNamespacesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:83` |
| `GET` | `v1/kubernetes/cluster/{cluster}/nodes` | `KubernetesController#GetNodesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:58` |
| `POST` | `v1/kubernetes/cluster/{cluster}/nodes` | `KubernetesController#GetNodesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:59` |
| `GET` | `v1/kubernetes/cluster/{cluster}/object/{objectType}` | `KubernetesController#GetItemAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:106` |
| `POST` | `v1/kubernetes/cluster/{cluster}/object/{objectType}` | `KubernetesController#GetItemAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:107` |
| `GET` | `v1/kubernetes/cluster/{cluster}/regions` | `KubernetesController#GetClusterRegionsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:34` |
| `POST` | `v1/kubernetes/cluster/{cluster}/regions` | `KubernetesController#GetClusterRegionsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/KubernetesController.cs:35` |
| `GET` | `v1/maintenance-windows` | `MaintenanceWindowController#GetMaintenanceWindowsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/MaintenanceWindowController.cs:61` |
| `DELETE` | `v1/provision/tenant/{tenantId}` | `ProvisionController#DeprovisionTenantAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ProvisionController.cs:78` |
| `GET` | `v1/provision/tenant/{tenantId}` | `ProvisionController#GetProvisioningStatusAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ProvisionController.cs:30` |
| `POST` | `v1/provision/tenant/{tenantId}` | `ProvisionController#ProvisionTenantAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ProvisionController.cs:54` |
| `DELETE` | `v1/provision/tenant/{tenantId}/catalog` | `ProvisionController#DeprovisionTenanCatalogAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ProvisionController.cs:125` |
| `POST` | `v1/provision/tenant/{tenantId}/catalog` | `ProvisionController#ProvisionTenantCatalogAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ProvisionController.cs:101` |
| `PUT` | `v1/{/securable` | `AccessController#UpdateSecurableAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:105` |
| `PUT` | `v1/{/securable/admin` | `AccessController#UpdateSecurableAccessAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:175` |
| `PUT` | `v1/{/securable/owner` | `AccessController#UpdateOwnerNameAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:138` |
| `POST` | `v1/{/securable/read` | `AccessController#GetSecurableAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:32` |
| `POST` | `v1/{/securable/read/admin` | `AccessController#GetSecurableAccessAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:73` |
| `POST` | `v1/{/{entityName}/artifact/check` | `AccessController#CheckArtifactAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:240` |
| `POST` | `v1/{/{entityName}/check` | `AccessController#CheckAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:210` |
| `GET` | `v1/{tenantId}/[controller]` | `ExposureSetController#GetExposureSetAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ExposureSetController.cs:59` |
| `GET` | `v1/{tenantId}/[controller]` | `ArchivesController#ListArchivesAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:55` |
| `GET` | `v1/{tenantId}/[controller]` | `EdmController#GetDatabasesAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:76` |
| `GET` | `v1/{tenantId}/[controller]` | `SqlInstancesController#ListSqlInstancesAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/SqlInstancesController.cs:31` |
| `POST` | `v1/{tenantId}/[controller]` | `EdmController#CreateExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:111` |
| `POST` | `v1/{tenantId}/[controller]` | `TransientDbController#CreateTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:54` |
| `POST` | `v1/{tenantId}/[controller]/accumulationAnalysis` | `ResultsController#CreateAccumulationAnalysis` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ResultsController.cs:86` |
| `PUT` | `v1/{tenantId}/[controller]/accumulationAnalysis/{analysisGuid}` | `ResultsController#UpdateAccumulationAnalysis` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ResultsController.cs:113` |
| `GET` | `v1/{tenantId}/[controller]/count` | `TransientDbController#GetTransientDbCountAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:203` |
| `POST` | `v1/{tenantId}/[controller]/createexposureset` | `ExposureSetController#CreateExposureSetAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ExposureSetController.cs:157` |
| `GET` | `v1/{tenantId}/[controller]/database` | `DataBridgeController#ListDatabasesAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/DataBridgeController.cs:47` |
| `GET` | `v1/{tenantId}/[controller]/database/withoutregistereditems` | `DataBridgeController#ListDatabasesWithoutRegisteredItemsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/DataBridgeController.cs:102` |
| `POST` | `v1/{tenantId}/[controller]/import` | `EdmController#ImportDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:203` |
| `POST` | `v1/{tenantId}/[controller]/import` | `TransientDbController#ImportTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:129` |
| `GET` | `v1/{tenantId}/[controller]/list` | `TransientDbController#GetTransientDbListAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:230` |
| `POST` | `v1/{tenantId}/[controller]/register` | `EdmController#RegisterDataBridgeDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:393` |
| `POST` | `v1/{tenantId}/[controller]/riskAnalysis` | `ResultsController#CreateRiskAnalysis` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ResultsController.cs:35` |
| `PUT` | `v1/{tenantId}/[controller]/riskAnalysis/{analysisGuid}` | `ResultsController#UpdateRiskAnalysis` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ResultsController.cs:60` |
| `POST` | `v1/{tenantId}/[controller]/sql-instances/{instanceName}/databases/{databaseName}/connection-string` | `DataBridgeController#CreateConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/DataBridgeController.cs:149` |
| `POST` | `v1/{tenantId}/[controller]/sql-instances/{instanceName}/databases/{databaseName}/quick-connection-string` | `DataBridgeController#CreateQuickConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/DataBridgeController.cs:183` |
| `POST` | `v1/{tenantId}/[controller]/sql-instances/{instanceName}/databases/{databaseName}/quick-connection-string` | `ManagedSqlDatabaseController#CreateQuickConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ManagedSqlDatabaseController.cs:27` |
| `DELETE` | `v1/{tenantId}/[controller]/{archiveId}` | `ArchivesController#DropArchiveAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:133` |
| `GET` | `v1/{tenantId}/[controller]/{archiveId}` | `ArchivesController#GetArchiveByIdAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:97` |
| `PATCH` | `v1/{tenantId}/[controller]/{archiveId}` | `ArchivesController#UpdateArchiveTypeAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:211` |
| `POST` | `v1/{tenantId}/[controller]/{archiveId}/restore` | `ArchivesController#RestoreArchiveAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:167` |
| `DELETE` | `v1/{tenantId}/[controller]/{databaseGuid}` | `TransientDbController#DropTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:174` |
| `POST` | `v1/{tenantId}/[controller]/{databaseGuid}/connection-string` | `TransientDbController#CreateConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:254` |
| `POST` | `v1/{tenantId}/[controller]/{databaseGuid}/export` | `TransientDbController#ExportTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/TransientDbController.cs:94` |
| `PATCH` | `v1/{tenantId}/[controller]/{exposureSetId}` | `ExposureSetController#PatchExposureSetAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/ExposureSetController.cs:92` |
| `DELETE` | `v1/{tenantId}/[controller]/{riGuid}` | `EdmController#DropExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:291` |
| `POST` | `v1/{tenantId}/[controller]/{riGuid}/connection-string` | `EdmController#CreateConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:323` |
| `DELETE` | `v1/{tenantId}/[controller]/{riGuid}/deregister` | `EdmController#DeregisterDataBridgeDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:439` |
| `POST` | `v1/{tenantId}/[controller]/{riGuid}/export` | `EdmController#ExportExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:156` |
| `POST` | `v1/{tenantId}/[controller]/{riGuid}/move` | `EdmController#MoveEdmAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:477` |
| `PUT` | `v1/{tenantId}/[controller]/{riGuid}/update` | `EdmController#UpdateDatabaseInfoAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:252` |
| `PATCH` | `v1/{tenantId}/[controller]/{riGuid}/update-metrics` | `EdmController#UpdateEdmMetrics` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/EdmController.cs:356` |
| `GET` | `v1/{tenantId}/[controller]/{serverName}` | `DataBridgeEdmController#GetEdmsOnServerAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/DataBridgeEdmController.cs:33` |
| `GET` | `v1/{tenantId}/[controller]/{serverName}/{databaseName}` | `DataBridgeEdmController#GetEdmForDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/DataBridgeEdmController.cs:65` |
| `PUT` | `v1/{tenantId}/catalog/[controller]/archives/{archiveId}` | `AdminController#UpdateArchiveEntitiesAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AdminController.cs:110` |
| `POST` | `v1/{tenantId}/catalog/[controller]/archives/{archiveId}/restore` | `AdminController#RestoreArchiveEntities` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AdminController.cs:61` |
| `PUT` | `v1/{tenantId}/catalog/[controller]/securable` | `AccessController#UpdateSecurableAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:242` |
| `PUT` | `v1/{tenantId}/catalog/[controller]/securable/admin` | `AccessController#UpdateSecurableAccessAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:295` |
| `POST` | `v1/{tenantId}/catalog/[controller]/securable/read` | `AccessController#GetSecurableAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:103` |
| `POST` | `v1/{tenantId}/catalog/[controller]/securable/read/admin` | `AccessController#GetSecurableAccessAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:187` |
| `DELETE` | `v1/{tenantId}/catalog/[controller]/securables/{securableId}/entities` | `AdminController#DeleteSecurableEntitiesAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AdminController.cs:22` |
| `PATCH` | `v1/{tenantId}/catalog/[controller]/{cardId}/admin` | `CardController#PatchCardAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.cs:34` |
| `POST` | `v1/{tenantId}/catalog/[controller]/{entityName}/check` | `AccessController#CheckAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:334` |
| `POST` | `v1/{tenantId}/catalog/[controller]/{entityName}/list` | `AccessController#ListAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:378` |
| `POST` | `v1/{tenantId}/edm/{riGuid}/[controller]` | `SnapshotController#CreateSnapshotAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/SnapshotController.cs:46` |
| `POST` | `v1/{tenantId}/edm/{riGuid}/[controller]/{snapshotId}/lease` | `SnapshotController#CreateSnapshotLeaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/SnapshotController.cs:72` |
| `DELETE` | `v1/{tenantId}/edm/{riGuid}/[controller]/{snapshotId}/lease/{leaseId}` | `SnapshotController#DeleteSnapshotLeaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/SnapshotController.cs:136` |
| `GET` | `v1/{tenantId}/edm/{riGuid}/[controller]/{snapshotId}/lease/{leaseId}` | `SnapshotController#GetSnapshotLeaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/SnapshotController.cs:118` |
| `GET` | `v1/{tenantId}/exposures` | `EntityVariationResource#getEntityVariations` | `${ApiConstants.SNAPSHOT_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:521` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` |
| `POST` | `v1/{tenantId}/exposures` | `EntityVariationResource#postEntityVariation` | `${ApiConstants.SNAPSHOT_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:157` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` |
| `POST` | `v1/{tenantId}/exposures//live-variations` | `EntityVariationResource#postLiveEntityVariations` | `${ApiConstants.SNAPSHOT_PATH}/${ApiConstants.LIVE_VARIATION_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:816` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:48` |
| `GET` | `v1/{tenantId}/exposures//{entityName}/variationjobs/{variationJobId}` | `EntityVariationResource#getEntityVariationJob` | `${ApiConstants.SNAPSHOT_PATH}/${ApiConstants.VARIATION_JOBS_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:405` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:35` |
| `POST` | `v1/{tenantId}/kms-key` | `KmsKeyController#CreateKmsKeyAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/KmsKeyController.cs:33` |
| `PUT` | `v1/{tenantId}/kms-key` | `KmsKeyController#UpdateKmsKeyAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/KmsKeyController.cs:65` |
| `GET` | `v1/{tenantId}/kms-key/{serverName}` | `KmsKeyController#GetKmsKeyAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/KmsKeyController.cs:96` |
| `GET` | `v1/{tenantId}/sql-instances` | `SqlInstancesController#ListSqlInstancesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:48` |
| `POST` | `v1/{tenantId}/sql-instances/force-migrate` | `SqlInstancesController#ForceMigrateSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:139` |
| `POST` | `v1/{tenantId}/sql-instances/force-restart` | `SqlInstancesController#ForceRestartSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:249` |
| `POST` | `v1/{tenantId}/sql-instances/force-upgrade` | `SqlInstancesController#ForceUpgradeSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:196` |
| `DELETE` | `v1/{tenantId}/sql-instances/{instanceName}` | `SqlInstancesController#DeleteSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:114` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}` | `SqlInstancesController#GetSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:69` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]` | `DatabasesController#ListDatabasesAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:118` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]` | `DatabasesController#CreateDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:55` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/bulk-delete` | `ArchivesController#BulkDropArchiveAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:308` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{DatabaseName}` | `DatabasesController#GetDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:89` |
| `PUT` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{DatabaseName}` | `DatabasesController#UpdateDatabaseMetaInfo` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:659` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{DatabaseName}/physical-file-exists` | `DatabasesController#GetPhysicalFileStatus` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:685` |
| `DELETE` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{archiveId}` | `ArchivesController#DropArchiveAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:79` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{archiveId}` | `ArchivesController#GetArchiveByIdAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:40` |
| `PATCH` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{archiveId}` | `ArchivesController#UpdateArchiveType` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:241` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{archiveId}/restore` | `ArchivesController#RestoreByIdArchiveAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:167` |
| `DELETE` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}` | `DatabasesController#DropDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:229` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/connection-string` | `DatabasesController#CreateConnectionStringAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:382` |
| `DELETE` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/connection-string/{connectionStringId}` | `DatabasesController#DeleteConnectionStringAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:504` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/connection-string/{connectionStringId}` | `DatabasesController#ExtendConnectionStringAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:466` |
| `DELETE` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/dropinactive` | `DatabasesController#DropIfInactiveDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:336` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/export` | `DatabasesController#ExportDatabase` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:147` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/import` | `DatabasesController#ImportDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:189` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/quick-connection-string` | `DatabasesController#QuickConnectionStringAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:423` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/shrink` | `DatabasesController#ShrinkDatabaseAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:574` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/shrink-file` | `DatabasesController#ShrinkDatabaseFileAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:541` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/[controller]/{databaseName}/sql-server-version` | `DatabasesController#GetSqlServerVersion` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/DatabasesController.cs:713` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/copy-to-archive` | `SqlInstancesController#CopyToArchiveFromSnapshotAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:376` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/dv-package` | `SqlInstancesController#GetDataVaultPackageDetailsForSqlInstance` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:494` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/encrypted-snapshot` | `SqlInstancesController#CreateEncryptedSnapshotAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:442` |
| `POST` | `v1/{tenantId}/sql-instances/{instanceName}/recreate-from-snapshot` | `SqlInstancesController#RecreateSqlInstanceFromSnapshotAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:328` |
| `PATCH` | `v1/{tenantId}/sql-instances/{instanceName}/reset-resource-usage` | `SqlInstancesController#ResetResourceUsageSqlInstanceAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:520` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/snapshots` | `SqlInstancesController#ListSqlInstanceSnapshotsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:298` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/sys-credentials` | `SqlInstancesController#GetSqlInstanceSysCredentialsAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:90` |
| `GET` | `v1/{tenantId}/sql-instances/{instanceName}/version` | `SqlInstancesController#GetSqlServerVersionAsync` | literal | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/SqlInstancesController.cs:572` |
| `POST` | `v2/{tenantId}/[controller]` | `EdmController#CreateExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/EdmController.cs:214` |
| `POST` | `v2/{tenantId}/[controller]` | `TransientDbController#CreateTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/TransientDbController.cs:81` |
| `GET` | `v2/{tenantId}/[controller]/database` | `DataBridgeController#ListDatabasesAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/DataBridgeController.cs:46` |
| `GET` | `v2/{tenantId}/[controller]/database/withoutregistereditems` | `DataBridgeController#ListDatabasesWithoutRegisteredItemsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/DataBridgeController.cs:101` |
| `POST` | `v2/{tenantId}/[controller]/import` | `EdmController#ImportDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/EdmController.cs:266` |
| `POST` | `v2/{tenantId}/[controller]/import` | `TransientDbController#ImportTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/TransientDbController.cs:166` |
| `POST` | `v2/{tenantId}/[controller]/register` | `EdmController#RegisterDataBridgeDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/EdmController.cs:97` |
| `POST` | `v2/{tenantId}/[controller]/registerwithguid` | `EdmController#RegisterDataBridgeDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/EdmController.cs:152` |
| `POST` | `v2/{tenantId}/[controller]/sql-instances/{instanceName}/databases/{databaseName}/connection-string` | `DataBridgeController#CreateConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/DataBridgeController.cs:150` |
| `POST` | `v2/{tenantId}/[controller]/sql-instances/{instanceName}/databases/{databaseName}/quick-connection-string` | `DataBridgeController#CreateQuickConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/DataBridgeController.cs:184` |
| `DELETE` | `v2/{tenantId}/[controller]/{databaseGuid}` | `TransientDbController#DropTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/TransientDbController.cs:51` |
| `DELETE` | `v2/{tenantId}/[controller]/{riGuid}` | `EdmController#DropExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v2/EdmController.cs:57` |
| `ANY` | `v2/{tenantId}/catalog/[controller]` | `CardController` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.cs:11` |
| `PUT` | `v2/{tenantId}/catalog/[controller]/securable` | `AccessController#UpdateSecurableAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/AccessController.cs:67` |
| `PUT` | `v2/{tenantId}/catalog/[controller]/securable/admin` | `AccessController#UpdateSecurableAccessAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/AccessController.cs:146` |
| `PUT` | `v2/{tenantId}/catalog/[controller]/securable/owner` | `AccessController#UpdateOwnerNameAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/AccessController.cs:98` |
| `POST` | `v2/{tenantId}/catalog/[controller]/securable/read` | `AccessController#GetSecurableAccessAsyncV2` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/AccessController.cs:175` |
| `POST` | `v2/{tenantId}/catalog/[controller]/securable/read/admin` | `AccessController#GetSecurableAccessAsAdminAsyncV2` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/AccessController.cs:202` |
| `POST` | `v3/{tenantId}/[controller]` | `EdmController#CreateExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/EdmController.cs:125` |
| `POST` | `v3/{tenantId}/[controller]` | `TransientDbController#CreateTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/TransientDbController.cs:63` |
| `GET` | `v3/{tenantId}/[controller]/database/withoutregistereditems` | `DataBridgeController#ListDatabasesWithoutRegisteredItemsAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/DataBridgeController.cs:41` |
| `POST` | `v3/{tenantId}/[controller]/import` | `EdmController#ImportDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/EdmController.cs:179` |
| `POST` | `v3/{tenantId}/[controller]/import` | `TransientDbController#ImportTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/TransientDbController.cs:104` |
| `POST` | `v3/{tenantId}/[controller]/registerwithguid` | `EdmController#RegisterDataBridgeDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/EdmController.cs:63` |
| `POST` | `v3/{tenantId}/[controller]/{databaseGuid:guid}/export` | `TransientDbController#ExportTransientDbAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/TransientDbController.cs:146` |
| `DELETE` | `v3/{tenantId}/[controller]/{dbGuid:guid}` | `TransientDbController#DropTransientDbJob` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/TransientDbController.cs:213` |
| `POST` | `v3/{tenantId}/[controller]/{dbGuid:guid}/connection-string` | `TransientDbController#CreateConnectionStringAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v3/TransientDbController.cs:182` |
| `ANY` | `v3/{tenantId}/catalog/[controller]` | `CardController` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.cs:11` |
| `POST` | `v4/{tenantId}/[controller]` | `EdmController#CreateExposureDatabaseAsync` | literal | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v4/EdmController.cs:58` |
| `ANY` | `{` | `CardController` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.cs:15` |
| `PATCH` | `{cardId}/admin` | `CardController#PatchCardAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Patch.cs:16` |
| `DELETE` | `{entityName}` | `CardController#DeleteCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:330` |
| `DELETE` | `{entityName}` | `CardController#DeleteCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:154` |
| `GET` | `{entityName}` | `CardController#GetCardsAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Query.cs:100` |
| `GET` | `{entityName}` | `CardController#GetCardsAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.Query.cs:99` |
| `GET` | `{entityName}` | `CardController#GetCardsAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Query.cs:20` |
| `POST` | `{entityName}` | `CardController#PostCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:60` |
| `POST` | `{entityName}` | `CardController#PostCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.Entity.cs:58` |
| `POST` | `{entityName}` | `CardController#PostCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.Entity.cs:59` |
| `POST` | `{entityName}` | `CardController#PostCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:22` |
| `PUT` | `{entityName}` | `CardController#PutCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:204` |
| `PUT` | `{entityName}` | `CardController#PutCardAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:120` |
| `POST` | `{entityName}/access` | `CardController#CheckAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Access.cs:36` |
| `POST` | `{entityName}/access` | `CardController#CheckAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Access.cs:14` |
| `GET` | `{entityName}/admin` | `CardController#GetCardsAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Query.cs:204` |
| `GET` | `{entityName}/admin` | `CardController#GetCardsAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.Query.cs:215` |
| `GET` | `{entityName}/admin` | `CardController#GetCardsAsAdminAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Query.cs:116` |
| `GET` | `{entityName}/aggregate` | `CardController#GetCardAggregateAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Query.cs:268` |
| `GET` | `{entityName}/aggregate` | `CardController#GetCardAggregateAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Query.cs:226` |
| `DELETE` | `{entityName}/artifact` | `CardController#DeleteArtifactAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:192` |
| `DELETE` | `{entityName}/artifact` | `CardController#DeleteArtifactAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:149` |
| `POST` | `{entityName}/artifact` | `CardController#PostArtifactAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:32` |
| `POST` | `{entityName}/artifact` | `CardController#PostArtifactAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:16` |
| `PUT` | `{entityName}/artifact` | `CardController#PutArtifactAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:119` |
| `PUT` | `{entityName}/artifact` | `CardController#PutArtifactAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:83` |
| `POST` | `{entityName}/artifact/access` | `CardController#CheckArtifactAccessAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Access.cs:46` |
| `DELETE` | `{entityName}/artifact/bulk` | `CardController#DeleteArtifactBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:229` |
| `DELETE` | `{entityName}/artifact/bulk` | `CardController#DeleteArtifactBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:178` |
| `POST` | `{entityName}/artifact/bulk` | `CardController#PostArtifactBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:87` |
| `POST` | `{entityName}/artifact/bulk` | `CardController#PostArtifactBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:46` |
| `PUT` | `{entityName}/artifact/bulk` | `CardController#PutArtifactBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:162` |
| `PUT` | `{entityName}/artifact/bulk` | `CardController#PutArtifactBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:112` |
| `DELETE` | `{entityName}/bulk` | `CardController#DeleteCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:396` |
| `DELETE` | `{entityName}/bulk` | `CardController#DeleteCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:269` |
| `POST` | `{entityName}/bulk` | `CardController#PostCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:168` |
| `POST` | `{entityName}/bulk` | `CardController#PostCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.Entity.cs:167` |
| `POST` | `{entityName}/bulk` | `CardController#PostCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.Entity.cs:167` |
| `POST` | `{entityName}/bulk` | `CardController#PostCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:185` |
| `PUT` | `{entityName}/bulk` | `CardController#PutCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:276` |
| `PUT` | `{entityName}/bulk` | `CardController#PutCardBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:230` |
| `GET` | `{entityName}/count` | `CardController#GetCardCountAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Query.cs:239` |
| `GET` | `{entityName}/count` | `CardController#GetCardCountAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Query.cs:184` |
| `GET` | `{entityName}/security` | `CardController#GetEntitySecuritySettingAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.Entity.cs:221` |
| `GET` | `{entityName}/security` | `CardController#GetEntitySecuritySettingAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:97` |
| `PUT` | `{entityName}/security` | `CardController#PutEntitySecuritySettingAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.Entity.cs:187` |
| `PUT` | `{entityName}/security` | `CardController#PutEntitySecuritySettingAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:54` |
| `DELETE` | `{entityName}/system` | `CardController#DeleteCardSystemAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:356` |
| `PUT` | `{entityName}/system` | `CardController#PutCardSystemAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:229` |
| `DELETE` | `{entityName}/system/bulk` | `CardController#DeleteCardSystemBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:419` |
| `PUT` | `{entityName}/system/bulk` | `CardController#PutCardSystemBulkAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:303` |
| `PUT` | `{entityName}/{cardId}/security` | `CardController#PutEntitySecuritySettingAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.Entity.cs:205` |
| `PUT` | `{entityName}/{cardId}/security` | `CardController#PutEntitySecuritySettingAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:75` |
| `PUT` | `{tenantId}/archives/{archiveId}` | `AdminController#UpdateArchiveEntitiesAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.Securable.cs:85` |
| `DELETE` | `{tenantId}/securables/{securableId}/entities` | `AdminController#DeleteSecurableEntitiesAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.Securable.cs:53` |
| `GET` | `{tenantId}/securables/{securableId}/entities` | `AdminController#GetSecurableEntitiesAsync` | literal | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.Securable.cs:16` |

## Duplicate fully-qualified names across modules

A repository that has these usually did not intend to. The resolver records every definition site and picks no winner.

- `AddJobType` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20230614173213_AddJobType.Designer.cs:16` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20230614173213_AddJobType.cs:7` `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20231213230641_AddJobType.Designer.cs:16` `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20231213230641_AddJobType.cs:7`
- `AddSubmittedAsToJobRecord` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20240124161538_AddSubmittedAsToJobRecord.Designer.cs:16` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20240124161538_AddSubmittedAsToJobRecord.cs:7` `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20240124163902_AddSubmittedAsToJobRecord.Designer.cs:16` `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20240124163902_AddSubmittedAsToJobRecord.cs:7`
- `AdminController` in catalog-service/RMS.UnifiedStore.Service.Catalog, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.Securable.cs:14` `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.cs:21` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.ConnectionString.cs:13`
- `AppEntitlementResponse` in core/RMS.UnifiedStore.Core, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/Contracts/AppEntitlementResponse.cs:3` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/TenantProvisioning/Http/Contracts/AppEntitlementResponse.cs:3`
- `Archive` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/Archive.cs:11` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/Archive.cs:8`
- `ArchiveAccess` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveAccess.cs:8` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/ArchiveAccess.cs:7`
- `ArchiveAccess#FromCatalogArchiveAccessData` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveAccess.cs:27` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/ArchiveAccess.cs:26`
- `ArchiveEdm` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveEdm.cs:9` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/ArchiveEdm.cs:7`
- `ArchiveEdm#FromCatalogArchiveEdmData` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveEdm.cs:79` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/ArchiveEdm.cs:77`
- `ArchiveNotFoundException` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Exceptions/ArchiveNotFoundException.cs:6` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Exceptions/ArchiveNotFoundException.cs:6`
- `ArchivesController` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:25` `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:27`
- `ArchivesController#DropArchiveAsync` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:80` `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:140`
- `ArchivesController#GetArchiveByIdAsync` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:41` `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:105`
- `BackgroundServiceConfiguration` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/BackgroundJobs/BackgroundServiceConfiguration.cs:7` `service-api/RMS.UnifiedStore.Service.Api/RecurringJobs/BackgroundServiceConfiguration.cs:3`
- `BulkAction` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/BulkRequest.cs:14` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/RegisterCardRequest.cs:40`
- `BulkRequest` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/BulkRequest.cs:6` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/RegisterCardRequest.cs:32`
- `CancelJobHandler` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Handlers/CancelJobHandler.cs:18` `service-api/RMS.UnifiedStore.Service.Api/Handlers/CancelJobHandler.cs:9`
- `CheckAccessRequest` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/CheckAccessRequest.cs:6` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/CheckAccessRequest.cs:7`
- `ConfigurationKeys` in managed-sql/RMS.UnifiedStore.Service.ManagedSql, service-api/RMS.UnifiedStore.Service.Api — `managed-sql/RMS.UnifiedStore.Service.ManagedSql/App/ConfigurationKeys.cs:3` `service-api/RMS.UnifiedStore.Service.Api/App/ConfigurationKeys.cs:3`
- `Constants` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Constants.cs:6` `core/RMS.UnifiedStore.Core.App/Constants.cs:5` `core/RMS.UnifiedStore.Core/Constants.cs:3` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Constants.cs:3`
- `Constants.BackgroundJob` in core/RMS.UnifiedStore.Core.App, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `core/RMS.UnifiedStore.Core.App/Constants.cs:19` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Constants.cs:23`
- `Constants.Catalog` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Constants.cs:8` `core/RMS.UnifiedStore.Core/Constants.cs:74`
- `Constants.Global` in catalog-service/RMS.UnifiedStore.Service.Catalog.Common, core/RMS.UnifiedStore.Core — `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Constants.cs:201` `core/RMS.UnifiedStore.Core/Constants.cs:5`
- `Constants.Header` in core/RMS.UnifiedStore.Core, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `core/RMS.UnifiedStore.Core/Constants.cs:17` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Constants.cs:5`
- `Constants.Middleware` in core/RMS.UnifiedStore.Core.App, managed-sql/RMS.UnifiedStore.Service.ManagedSql — `core/RMS.UnifiedStore.Core.App/Constants.cs:14` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Constants.cs:19`

## Where to go next

- [`unknowns.md`](unknowns.md) — what this run could not establish. Read it before trusting anything above.
- [`dataflow.md`](dataflow.md) — how a record actually travels, including edges no import expresses.
- `cdp query` — the same state, queryable. `query symbol DServer`, `query table server`, `query routes`, `query paths --to table:server`.
