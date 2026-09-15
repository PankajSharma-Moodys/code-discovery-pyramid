# `exposure-snapshot/snapshot-sdk`

50 tracked files, 7,932 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-sdk/(files+2)`, `root/exposure-snapshot/snapshot-sdk/src/main/java`, `root/exposure-snapshot/snapshot-sdk/src/main/scala`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (1 refs), `client-java/uds-client` (12 refs), `exposure-snapshot/snapshot-common` (20 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (1 refs)

**Imported by:** `client-java/uds-client` (2 refs), `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/ods-domain-data` (1 refs), `exposure-snapshot/snapshot-api` (25 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (2 refs), `exposure-snapshot/snapshot-task-delete` (3 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ExternalApiCallHelper` | class | 10 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/ExternalApiCallHelper.java:20` |
| `S3ConnectionManager` | class | 3 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/S3ConnectionManager.java:25` |
| `UdsSdkHelper` | class | 3 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/UdsSdkHelper.java:31` |
| `RMSStorageWrapper` | interface | 2 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageWrapper.java:19` |
| `S3SyncWrapper` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/impl/S3SyncWrapper.java:33` |
| `RMSStorageFactory` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageFactory.java:12` |
| `AccountManager` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/dao/AccountManager.java:14` |
| `PortfolioManager` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/dao/PortfolioManager.java:11` |
| `TreatyManager` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/dao/TreatyManager.java:13` |
| `DataSourceManager` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/db/DataSourceManager.java:14` |
| `DataHelper` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/DataHelper.java:8` |
| `S3AsyncWrapper` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/impl/S3AsyncWrapper.java:58` |
| `SurrogateJobIdPathDetails` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/SurrogateJobIdPathDetails.java:5` |
| `AccountService` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/services/AccountService.java:13` |
| `PortfolioService` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/services/PortfolioService.java:15` |
| `ExposureVariationJobs` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/ExposureVariationJobs.java:5` |
| `ExposureVariations` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/ExposureVariations.java:5` |
| `RMSStorageBuilder` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageBuilder.java:7` |
| `DataSourceErrorCode` | enum | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/datasource/DataSourceErrorCode.java:7` |
| `ReadWriteDataSource` | interface | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/db/ReadWriteDataSource.java:7` |
| `ReadWriteDataSourceImpl` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/db/ReadWriteDataSourceImpl.java:8` |
| `HelperFile` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/HelperFile.java:3` |
| `DatabaseBase` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/DatabaseBase.java:7` |
| `ManagedDatabase` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/ManagedDatabase.java:7` |
| `VariationJobDetails` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/VariationJobDetails.java:3` |
| `EdmQueryService` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/EdmQueryService.java:12` |
| `ExposureVariationsDetailsJson` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/ExposureVariationsDetailsJson.java:3` |
| `QueryEdmResult` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/QueryEdmResult.java:3` |
| `TaskResourcesHelper` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/TaskResourcesHelper.java:8` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-sdk/(files+2)` | 6 | 536 | structural only |
| `root/exposure-snapshot/snapshot-sdk/src/main/java` | 30 | 3,933 | structural only |
| `root/exposure-snapshot/snapshot-sdk/src/main/scala` | 14 | 3,463 | structural only |
