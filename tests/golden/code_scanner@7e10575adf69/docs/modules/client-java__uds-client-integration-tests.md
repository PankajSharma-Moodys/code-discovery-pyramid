# `client-java/uds-client-integration-tests`

128 tracked files, 26,418 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/client-java/uds-client-integration-tests/(files+5)`, `root/client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/(files+5)`, `root/client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog`, `root/client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests`, `root/client-java/uds-client-integration-tests/src/test/resources/automation`, `root/client-java/uds-client-integration-tests/src/test/resources/docs`, `root/client-java/uds-client-integration-tests/src/test/resources/rdm-edm-dbfiles`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (64 refs), `client-java/eih-client` (2 refs), `client-java/uds-client` (170 refs), `exposure-snapshot/snapshot-common` (9 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (9 refs), `exposure-snapshot/snapshot-sdk` (9 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `TestContext` | class | 32 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:13` |
| `AccessTokenGenerator` | class | 25 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/AccessTokenGenerator.java:7` |
| `ServiceApiTestHelper` | class | 19 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/ServiceApiTestHelper.java:41` |
| `TestResponse` | record | 17 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/model/TestResponse.java:6` |
| `AutomationKeys` | class | 15 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/AutomationKeys.java:3` |
| `UniqueTestNames` | class | 15 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/UniqueTestNames.java:10` |
| `TestExecutionReport` | class | 9 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/report/TestExecutionReport.java:24` |
| `TestCase` | class | 8 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/model/TestCase.java:10` |
| `SmlUserSetupService` | class | 7 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/SmlUserSetupService.java:39` |
| `CatalogAutomationHelper` | class | 7 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/CatalogAutomationHelper.java:35` |
| `EnvironmentKeys` | enum | 6 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/EnvironmentKeys.java:3` |
| `TestHttpClient` | class | 5 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestHttpClient.java:28` |
| `ServiceApiAutomationHelper` | class | 5 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/ServiceApiAutomationHelper.java:13` |
| `BaseRegressionTest` | class | 4 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/BaseRegressionTest.java:20` |
| `UserContext` | record | 4 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/model/UserContext.java:5` |
| `JiraTicketDetails` | record | 3 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/model/JiraTicketDetails.java:6` |
| `ManagedSqlAutomationHelper` | class | 2 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/managedsql/ManagedSqlAutomationHelper.java:28` |
| `TestResult` | record | 2 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/report/TestResult.java:6` |
| `JiraNotificationHelper` | class | 2 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/utilities/JiraNotificationHelper.java:25` |
| `CatalogAccessApiTest` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/tests/CatalogAccessApiTest.java:32` |
| `CatalogSecurableApiTest` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/tests/CatalogSecurableApiTest.java:24` |
| `CreateEdmRequest` | record | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/model/CreateEdmRequest.java:5` |
| `TestCases` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/model/TestCases.java:8` |
| `TeamsReportTemplate` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/report/TeamsReportTemplate.java:3` |
| `TestResultCollectorListener` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/report/TestResultCollectorListener.java:17` |
| `AutomationS3Helper` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/utilities/AutomationS3Helper.java:14` |
| `JiraTicketHelper` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/utilities/JiraTicketHelper.java:16` |
| `QEServiceConstants` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/utilities/QEServiceConstants.java:10` |
| `QEServiceHelper` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/utilities/QEServiceHelper.java:19` |
| `TeamsNotificationHelper` | class | 1 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/utilities/TeamsNotificationHelper.java:15` |
| `AutomationDebugTool` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/AutomationDebugTool.java:40` |
| `PipelineTestRunner` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/PipelineTestRunner.java:11` |
| `ApiKeyTokenGenerator` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/ApiKeyTokenGenerator.java:40` |
| `AwsSettings` | record | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:267` |
| `ParsedCondition` | record | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/CatalogAutomationHelper.java:418` |
| `BusinessHierarchyEntityCrudTest` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/tests/BusinessHierarchyEntityCrudTest.java:22` |
| `CatalogAdminArchiveApiTest` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/tests/CatalogAdminArchiveApiTest.java:34` |
| `CatalogCardArtifactApiTest` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/tests/CatalogCardArtifactApiTest.java:33` |
| `CatalogEntityCrudTest` | class | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog/tests/CatalogEntityCrudTest.java:22` |
| `EdmRef` | record | 0 | `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/managedsql/ManagedSqlAutomationHelper.java:79` |

_34 more; use `cdp query module client-java/uds-client-integration-tests`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/client-java/uds-client-integration-tests/(files+5)` | 27 | 5,935 | structural only |
| `root/client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/(files+5)` | 19 | 3,364 | structural only |
| `root/client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/datacatalog` | 7 | 3,926 | structural only |
| `root/client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests` | 25 | 8,420 | structural only |
| `root/client-java/uds-client-integration-tests/src/test/resources/automation` | 6 | 3,030 | structural only |
| `root/client-java/uds-client-integration-tests/src/test/resources/docs` | 23 | 1,743 | structural only |
| `root/client-java/uds-client-integration-tests/src/test/resources/rdm-edm-dbfiles` | 21 | 0 | structural only |
