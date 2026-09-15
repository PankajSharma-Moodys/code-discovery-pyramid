# `automation/api-automation`

42 tracked files, 7,178 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/automation/api-automation/(files+10)`, `root/automation/api-automation/src/main/java/com/rms/uds/tests`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ApiListener` | class | 8 | `automation/api-automation/src/main/java/com/rms/uds/listener/ApiListener.java:27` |
| `AuthTokenUtil` | class | 5 | `automation/api-automation/src/main/java/com/rms/uds/model/AuthTokenUtil.java:9` |
| `JobService` | interface | 4 | `automation/api-automation/src/main/java/com/rms/uds/interfaces/JobService.java:5` |
| `SecurableInput` | class | 4 | `automation/api-automation/src/main/java/com/rms/uds/objects/input/dataCatalog/SecurableInput.java:6` |
| `JobServiceImpl` | class | 3 | `automation/api-automation/src/main/java/com/rms/uds/util/datacatalog/JobServiceImpl.java:15` |
| `SecurableApi` | class | 2 | `automation/api-automation/src/main/java/com/rms/uds/apis/dataCatalog/SecurableApi.java:22` |
| `UdsApi` | class | 2 | `automation/api-automation/src/main/java/com/rms/uds/apis/managedSql/UdsApi.java:11` |
| `ManagedSqlPayloadRepository` | class | 2 | `automation/api-automation/src/main/java/com/rms/uds/bal/managedSql/ManagedSqlPayloadRepository.java:3` |
| `EnvConfig` | class | 2 | `automation/api-automation/src/main/java/com/rms/uds/config/EnvConfig.java:23` |
| `CrudEntitiesTestcase` | class | 2 | `automation/api-automation/src/main/java/com/rms/uds/objects/testcases/dataCatalog/CrudEntitiesTestcase.java:7` |
| `ConfigManager` | class | 1 | `automation/api-automation/src/main/java/com/rms/uds/config/ConfigManager.java:8` |
| `AccessApiTestcase` | class | 1 | `automation/api-automation/src/main/java/com/rms/uds/objects/testcases/dataCatalog/AccessApiTestcase.java:6` |
| `CatalogEntitiesCrudTestcase` | class | 1 | `automation/api-automation/src/main/java/com/rms/uds/objects/testcases/dataCatalog/CatalogEntitiesCrudTestcase.java:6` |
| `SecurableApiTestcase` | class | 1 | `automation/api-automation/src/main/java/com/rms/uds/objects/testcases/dataCatalog/SecurableApiTestcase.java:6` |
| `EdmCrudTestcase` | class | 1 | `automation/api-automation/src/main/java/com/rms/uds/objects/testcases/managedSql/EdmCrudTestcase.java:7` |
| `TransientDbCrudTestcase` | class | 1 | `automation/api-automation/src/main/java/com/rms/uds/objects/testcases/managedSql/TransientDbCrudTestcase.java:7` |
| `AccessApi` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/apis/dataCatalog/AccessApi.java:16` |
| `EntityApi` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/apis/dataCatalog/EntityApi.java:12` |
| `CommonRequest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/bal/dataCatalog/CommonRequest.java:11` |
| `EndpointManager` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/bal/dataCatalog/EndpointManager.java:6` |
| `PayloadRepository` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/bal/dataCatalog/PayloadRepository.java:7` |
| `AutomationConstants` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/constants/AutomationConstants.java:6` |
| `TestSuiteExecutor` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/TestSuiteExecutor.java:17` |
| `AccessApiTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/AccessApiTest.java:45` |
| `CatalogApiTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/CatalogApiTest.java:35` |
| `CatalogEntitiesCrudTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/CatalogEntitiesCrudTest.java:61` |
| `CrudEntitiesTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/CrudEntitiesTest.java:41` |
| `SecurableApiTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/SecurableApiTest.java:69` |
| `EdmCrudTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/EdmCrudTest.java:31` |
| `SmokeSuite` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:37` |
| `ExportDatabaseRequest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:536` |
| `ExportToType` | enum | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:378` |
| `ImportDatabaseRequest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:387` |
| `ImportEdmRequestv3` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:480` |
| `ImportFromType` | enum | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:369` |
| `Pair` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:344` |
| `SmokeSuiteTestResult` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:1602` |
| `TransientDbCrudTest` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/TransientDbCrudTest.java:31` |
| `ApiUtil` | class | 0 | `automation/api-automation/src/main/java/com/rms/uds/util/datacatalog/ApiUtil.java:10` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/automation/api-automation/(files+10)` | 33 | 2,395 | structural only |
| `root/automation/api-automation/src/main/java/com/rms/uds/tests` | 9 | 4,783 | structural only |
