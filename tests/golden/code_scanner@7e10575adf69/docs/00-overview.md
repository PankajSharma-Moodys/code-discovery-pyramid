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
| Symbols declared | 12,949 |
| HTTP routes | 43 |

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
| Observed (imports) | 58 |

Observed dependency levels (each depends only on those above it):

```
L0  (root), automation, automation/api-automation, catalog-service/RMS.UnifiedStore.Service.Catalog, catalog-service/RMS.UnifiedStore.Service.Catalog.Common, catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine, catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests, catalog-service/RMS.UnifiedStore.Service.Catalog.Tests, catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli, client-dotnet/RMS.UnifiedStore.Client, client-java, client-java/client-core, core/RMS.UnifiedStore.Core, core/RMS.UnifiedStore.Core.App, core/RMS.UnifiedStore.Core.App.Tests, core/RMS.UnifiedStore.Core.Tests, exposure-snapshot, exposure-snapshot/download-exposure, exposure-snapshot/entity-variation-task, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy, exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-migration, exposure-snapshot/snapshot-smoketest, exposure-snapshot/swagger-resource, managed-sql/RMS.UnifiedStore.Service.ManagedSql, managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests, ms-sql-java, ms-sql-java/downgrade-processor, service-api/RMS.UnifiedStore.Service.Api, service-api/RMS.UnifiedStore.Service.Api.Common, service-api/RMS.UnifiedStore.Service.Api.Integration.Tests, service-api/RMS.UnifiedStore.Service.Api.Tests, sql-pool, sql-pool/sql-pool-api-client, sql-pool/sql-pool-common, tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB, tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests
L1  client-java/eih-client, client-java/uds-client, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-developer-utils, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-legacy/snapshot-legacy-partition, exposure-snapshot/snapshot-legacy/snapshot-legacy-transform, exposure-snapshot/snapshot-sdk, sql-pool/sql-pool-dal, sql-pool/sql-pool-provision, sql-pool/sql-pool-setup
L2  client-java/uds-client-integration-tests, exposure-snapshot/idempotency-filter, exposure-snapshot/snapshot-filter-query-service, exposure-snapshot/snapshot-task-create, exposure-snapshot/snapshot-task-delete, sql-pool/sql-pool-integrationtest, sql-pool/sql-pool-service, sql-pool/sql-pool-smoketest
L3  exposure-snapshot/snapshot-workflow-service, sql-pool/sql-pool-api, sql-pool/sql-pool-manager
L4  exposure-snapshot/snapshot-api
```

### Imported but not declared

These compile by transitive resolution and will break on a dependency bump.

- `client-java/uds-client` -> `exposure-snapshot/ods-domain-data`
- `client-java/uds-client` -> `exposure-snapshot/snapshot-sdk`
- `client-java/uds-client-integration-tests` -> `client-java/client-core`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-common`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `client-java/uds-client-integration-tests` -> `exposure-snapshot/snapshot-sdk`
- `exposure-snapshot/idempotency-filter` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/ods-domain-data` -> `client-java/uds-client`
- `exposure-snapshot/ods-domain-data` -> `exposure-snapshot/snapshot-sdk`
- `exposure-snapshot/snapshot-api` -> `client-java/client-core`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/snapshot-filter-query-service`
- `exposure-snapshot/snapshot-api` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-sdk` -> `client-java/client-core`
- `exposure-snapshot/snapshot-sdk` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `exposure-snapshot/snapshot-task-delete` -> `client-java/uds-client`
- `exposure-snapshot/snapshot-task-delete` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `exposure-snapshot/snapshot-workflow-service` -> `exposure-snapshot/snapshot-common`

### Declared but never imported

Candidate stale dependencies. Note that a dependency on a module whose sources are generated at build time will appear here legitimately — the imports exist, but not in git.

- `exposure-snapshot` -> `client-java/uds-client`
- `exposure-snapshot/download-exposure` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/download-exposure` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/download-exposure` -> `exposure-snapshot/snapshot-sdk`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/ods-domain-data`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/snapshot-legacy/snapshot-legacy-core`
- `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` -> `exposure-snapshot/snapshot-sdk`
- `exposure-snapshot/snapshot-migration` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-sdk` -> `exposure-snapshot/snapshot-filter-query-service`
- `exposure-snapshot/snapshot-smoketest` -> `exposure-snapshot/snapshot-common`
- `exposure-snapshot/snapshot-smoketest` -> `exposure-snapshot/snapshot-sdk`
- `sql-pool/sql-pool-integrationtest` -> `sql-pool/sql-pool-api-client`
- `sql-pool/sql-pool-setup` -> `sql-pool/sql-pool-provision`
- `sql-pool/sql-pool-smoketest` -> `sql-pool/sql-pool-api-client`

## Modules

| Module | Files | LOC | Depends on | Depended on by |
|---|---|---|---|---|
| [`service-api/RMS.UnifiedStore.Service.Api`](modules/service-api__RMS.UnifiedStore.Service.Api.md) | 1047 | 615,149 | — | — |
| [`managed-sql/RMS.UnifiedStore.Service.ManagedSql`](modules/managed-sql__RMS.UnifiedStore.Service.ManagedSql.md) | 518 | 73,362 | — | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Common`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Common.md) | 375 | 41,806 | — | — |
| [`client-java/uds-client`](modules/client-java__uds-client.md) | 248 | 36,295 | client-java/client-core, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-sdk | client-java/uds-client-integration-tests, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-task-create, exposure-snapshot/snapshot-task-delete |
| [`exposure-snapshot/snapshot-common`](modules/exposure-snapshot__snapshot-common.md) | 220 | 16,249 | — | client-java/uds-client-integration-tests, exposure-snapshot/idempotency-filter, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-developer-utils, exposure-snapshot/snapshot-filter-query-service, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-legacy/snapshot-legacy-partition, exposure-snapshot/snapshot-legacy/snapshot-legacy-transform, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-task-create, exposure-snapshot/snapshot-task-delete, exposure-snapshot/snapshot-workflow-service |
| [`exposure-snapshot/entity-variation-task`](modules/exposure-snapshot__entity-variation-task.md) | 164 | 16,916 | — | — |
| [`service-api/RMS.UnifiedStore.Service.Api.Tests`](modules/service-api__RMS.UnifiedStore.Service.Api.Tests.md) | 162 | 51,363 | — | — |
| [`client-java/uds-client-integration-tests`](modules/client-java__uds-client-integration-tests.md) | 128 | 26,418 | client-java/client-core, client-java/eih-client, client-java/uds-client, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-sdk | — |
| [`exposure-snapshot/snapshot-api`](modules/exposure-snapshot__snapshot-api.md) | 124 | 17,382 | client-java/client-core, client-java/uds-client, exposure-snapshot/idempotency-filter, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-filter-query-service, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-workflow-service, exposure-snapshot/swagger-resource | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.md) | 115 | 11,133 | — | — |
| [`managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests`](modules/managed-sql__RMS.UnifiedStore.Service.ManagedSql.Tests.md) | 108 | 31,246 | — | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Engine.md) | 103 | 9,068 | — | — |
| [`sql-pool/sql-pool-common`](modules/sql-pool__sql-pool-common.md) | 90 | 6,400 | — | sql-pool/sql-pool-api, sql-pool/sql-pool-dal, sql-pool/sql-pool-integrationtest, sql-pool/sql-pool-manager, sql-pool/sql-pool-provision, sql-pool/sql-pool-service, sql-pool/sql-pool-setup, sql-pool/sql-pool-smoketest |
| [`sql-pool/sql-pool-integrationtest`](modules/sql-pool__sql-pool-integrationtest.md) | 85 | 28,758 | sql-pool/sql-pool-common, sql-pool/sql-pool-dal | — |
| [`core/RMS.UnifiedStore.Core`](modules/core__RMS.UnifiedStore.Core.md) | 78 | 2,855 | — | — |
| [`sql-pool/sql-pool-manager`](modules/sql-pool__sql-pool-manager.md) | 74 | 8,554 | sql-pool/sql-pool-common, sql-pool/sql-pool-provision, sql-pool/sql-pool-service | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Common.Tests.md) | 67 | 10,656 | — | — |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Engine.Tests.md) | 57 | 6,789 | — | — |
| [`sql-pool/sql-pool-provision`](modules/sql-pool__sql-pool-provision.md) | 52 | 2,420 | sql-pool/sql-pool-common | sql-pool/sql-pool-manager, sql-pool/sql-pool-smoketest |
| [`exposure-snapshot/snapshot-sdk`](modules/exposure-snapshot__snapshot-sdk.md) | 50 | 7,932 | client-java/client-core, client-java/uds-client, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core | client-java/uds-client, client-java/uds-client-integration-tests, exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-task-delete |
| [`exposure-snapshot`](modules/exposure-snapshot.md) | 49 | 247,920 | — | — |
| [`sql-pool/sql-pool-api`](modules/sql-pool__sql-pool-api.md) | 49 | 4,038 | sql-pool/sql-pool-common, sql-pool/sql-pool-service | — |
| [`sql-pool/sql-pool-setup`](modules/sql-pool__sql-pool-setup.md) | 49 | 1,759 | sql-pool/sql-pool-common | — |
| [`exposure-snapshot/snapshot-smoketest`](modules/exposure-snapshot__snapshot-smoketest.md) | 43 | 4,784 | — | — |
| [`automation/api-automation`](modules/automation__api-automation.md) | 42 | 7,178 | — | — |
| [`catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli`](modules/catalog-service__RMS.UnifiedStore.Tools.Catalog.Cli.md) | 39 | 4,484 | — | — |
| [`exposure-snapshot/snapshot-workflow-service`](modules/exposure-snapshot__snapshot-workflow-service.md) | 32 | 2,621 | exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-filter-query-service | exposure-snapshot/snapshot-api |
| [`exposure-snapshot/ods-domain-data`](modules/exposure-snapshot__ods-domain-data.md) | 31 | 2,550 | client-java/uds-client, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-sdk | client-java/uds-client, exposure-snapshot/idempotency-filter, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-filter-query-service |
| [`client-java/client-core`](modules/client-java__client-core.md) | 30 | 1,595 | — | client-java/eih-client, client-java/uds-client, client-java/uds-client-integration-tests, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-sdk |
| [`ms-sql-java/downgrade-processor`](modules/ms-sql-java__downgrade-processor.md) | 26 | 57,123 | — | — |
| [`core/RMS.UnifiedStore.Core.App`](modules/core__RMS.UnifiedStore.Core.App.md) | 23 | 924 | — | — |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-task`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-task.md) | 23 | 4,670 | — | — |
| [`exposure-snapshot/swagger-resource`](modules/exposure-snapshot__swagger-resource.md) | 23 | 11,889 | — | exposure-snapshot/snapshot-api |
| [`sql-pool/sql-pool-service`](modules/sql-pool__sql-pool-service.md) | 23 | 5,821 | sql-pool/sql-pool-common, sql-pool/sql-pool-dal | sql-pool/sql-pool-api, sql-pool/sql-pool-manager |
| [`exposure-snapshot/snapshot-task-create`](modules/exposure-snapshot__snapshot-task-create.md) | 22 | 1,430 | client-java/uds-client, exposure-snapshot/snapshot-common | — |
| [`sql-pool/sql-pool-dal`](modules/sql-pool__sql-pool-dal.md) | 21 | 1,801 | sql-pool/sql-pool-common | sql-pool/sql-pool-integrationtest, sql-pool/sql-pool-service |
| [`sql-pool`](modules/sql-pool.md) | 20 | 2,497 | — | — |
| [`exposure-snapshot/download-exposure`](modules/exposure-snapshot__download-exposure.md) | 19 | 3,510 | — | — |
| [`exposure-snapshot/snapshot-filter-query-service`](modules/exposure-snapshot__snapshot-filter-query-service.md) | 19 | 2,217 | exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-common | exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-workflow-service |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-core`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-core.md) | 18 | 992 | exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-sdk | client-java/uds-client-integration-tests, exposure-snapshot/snapshot-api, exposure-snapshot/snapshot-sdk, exposure-snapshot/snapshot-task-delete |
| [`catalog-service/RMS.UnifiedStore.Service.Catalog.Tests`](modules/catalog-service__RMS.UnifiedStore.Service.Catalog.Tests.md) | 17 | 3,000 | — | — |
| [`exposure-snapshot/snapshot-migration`](modules/exposure-snapshot__snapshot-migration.md) | 15 | 732 | — | — |
| [`service-api/RMS.UnifiedStore.Service.Api.Integration.Tests`](modules/service-api__RMS.UnifiedStore.Service.Api.Integration.Tests.md) | 15 | 2,305 | — | — |
| [`sql-pool/sql-pool-smoketest`](modules/sql-pool__sql-pool-smoketest.md) | 12 | 887 | sql-pool/sql-pool-common, sql-pool/sql-pool-provision | — |
| [`client-java/eih-client`](modules/client-java__eih-client.md) | 11 | 443 | client-java/client-core | client-java/uds-client-integration-tests |
| [`tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB`](modules/tests__performance__catalog-data-model__RMS.UnifiedStore.Tests.Performance.DataModel.DB.md) | 9 | 365 | — | — |
| [`core/RMS.UnifiedStore.Core.Tests`](modules/core__RMS.UnifiedStore.Core.Tests.md) | 8 | 1,093 | — | — |
| [`exposure-snapshot/idempotency-filter`](modules/exposure-snapshot__idempotency-filter.md) | 8 | 478 | exposure-snapshot/ods-domain-data, exposure-snapshot/snapshot-common | exposure-snapshot/snapshot-api |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-accumulation.md) | 8 | 605 | — | — |
| [`exposure-snapshot/snapshot-task-delete`](modules/exposure-snapshot__snapshot-task-delete.md) | 6 | 428 | client-java/uds-client, exposure-snapshot/snapshot-common, exposure-snapshot/snapshot-legacy/snapshot-legacy-core, exposure-snapshot/snapshot-sdk | — |
| [`service-api/RMS.UnifiedStore.Service.Api.Common`](modules/service-api__RMS.UnifiedStore.Service.Api.Common.md) | 5 | 311 | — | — |
| [`core/RMS.UnifiedStore.Core.App.Tests`](modules/core__RMS.UnifiedStore.Core.App.Tests.md) | 4 | 226 | — | — |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-partition`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-partition.md) | 4 | 163 | exposure-snapshot/snapshot-common | — |
| [`exposure-snapshot/snapshot-legacy/snapshot-legacy-transform`](modules/exposure-snapshot__snapshot-legacy__snapshot-legacy-transform.md) | 4 | 196 | exposure-snapshot/snapshot-common | — |
| [`ms-sql-java`](modules/ms-sql-java.md) | 4 | 146 | — | — |
| [`client-java`](modules/client-java.md) | 3 | 193 | — | — |
| [`automation`](modules/automation.md) | 2 | 40 | — | — |
| [`client-dotnet/RMS.UnifiedStore.Client`](modules/client-dotnet__RMS.UnifiedStore.Client.md) | 2 | 15 | — | — |
| [`exposure-snapshot/snapshot-developer-utils`](modules/exposure-snapshot__snapshot-developer-utils.md) | 2 | 189 | exposure-snapshot/snapshot-common | — |
| [`sql-pool/sql-pool-api-client`](modules/sql-pool__sql-pool-api-client.md) | 2 | 62 | — | — |
| [`tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests`](modules/tests__performance__catalog-data-model__RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests.md) | 2 | 86 | — | — |
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
| `GET` | `internal/variation/v1/exposurevariations` | `InternalVariationResource#getExposureVariations` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:196` |
| `GET` | `internal/variation/v1/exposurevariations/admin` | `InternalVariationResource#getExposureVariationsAsAdmin` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:281` |
| `GET` | `internal/variation/v1/exposurevariations/{variationId}` | `InternalVariationResource#getExposureVariation` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:55` |
| `GET` | `internal/variation/v1/exposurevariations/{variationId}/admin` | `InternalVariationResource#getExposureVariationAsAdmin` | literal | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:129` |
| `GET` | `v1/{tenantId}/exposures` | `EntityVariationResource#getEntityVariations` | `${ApiConstants.SNAPSHOT_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:521` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` |
| `POST` | `v1/{tenantId}/exposures` | `EntityVariationResource#postEntityVariation` | `${ApiConstants.SNAPSHOT_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:157` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` |
| `POST` | `v1/{tenantId}/exposures//live-variations` | `EntityVariationResource#postLiveEntityVariations` | `${ApiConstants.SNAPSHOT_PATH}/${ApiConstants.LIVE_VARIATION_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:816` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:48` |
| `GET` | `v1/{tenantId}/exposures//{entityName}/variationjobs/{variationJobId}` | `EntityVariationResource#getEntityVariationJob` | `${ApiConstants.SNAPSHOT_PATH}/${ApiConstants.VARIATION_JOBS_PATH}` | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:405` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:35` |

## Duplicate fully-qualified names across modules

A repository that has these usually did not intend to. The resolver records every definition site and picks no winner.

- `com.rms.unifiedstore.utility.ZipUtility` in exposure-snapshot/download-exposure, exposure-snapshot/snapshot-legacy/snapshot-legacy-core — `exposure-snapshot/download-exposure/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:14` `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:14`
- `com.rms.unifiedstore.utility.ZipUtility#zipDirectory` in exposure-snapshot/download-exposure, exposure-snapshot/snapshot-legacy/snapshot-legacy-core — `exposure-snapshot/download-exposure/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:18` `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:18`
- `com.rms.unifiedstore.utility.ZipUtility.LOGGER` in exposure-snapshot/download-exposure, exposure-snapshot/snapshot-legacy/snapshot-legacy-core — `exposure-snapshot/download-exposure/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:15` `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:15`
- `com.rms.unifiedstore.utility.ZipUtility.UNDER_SCORE` in exposure-snapshot/download-exposure, exposure-snapshot/snapshot-legacy/snapshot-legacy-core — `exposure-snapshot/download-exposure/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:16` `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:16`

## Where to go next

- [`unknowns.md`](unknowns.md) — what this run could not establish. Read it before trusting anything above.
- [`dataflow.md`](dataflow.md) — how a record actually travels, including edges no import expresses.
- `cdp query` — the same state, queryable. `query symbol DServer`, `query table server`, `query routes`, `query paths --to table:server`.
