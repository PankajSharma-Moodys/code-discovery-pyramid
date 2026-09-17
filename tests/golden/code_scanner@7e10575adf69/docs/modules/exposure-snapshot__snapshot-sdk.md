# `exposure-snapshot/snapshot-sdk`

50 tracked files, 7,932 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-sdk/(files+2)`, `root/exposure-snapshot/snapshot-sdk/src/main/java`, `root/exposure-snapshot/snapshot-sdk/src/main/scala`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (1 refs), `client-java/uds-client` (11 refs), `exposure-snapshot/snapshot-common` (31 refs)

**Imported by:** `client-java/uds-client` (2 refs), `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/download-exposure` (14 refs), `exposure-snapshot/ods-domain-data` (1 refs), `exposure-snapshot/snapshot-api` (25 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` (10 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (2 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` (26 refs), `exposure-snapshot/snapshot-smoketest` (6 refs), `exposure-snapshot/snapshot-task-delete` (3 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `DbCommunicator` | class | 17 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/DbCommunicator.scala:24` |
| `ExternalApiCallHelper` | class | 10 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/ExternalApiCallHelper.java:20` |
| `AsyncS3UploadDownloader` | class | 6 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/AsyncS3UploadDownloader.scala:15` |
| `DataSourceManager` | class | 5 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/db/DataSourceManager.java:14` |
| `UdsSdkHelper` | class | 5 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/UdsSdkHelper.java:31` |
| `RMSStorageFactory` | class | 4 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageFactory.java:12` |
| `ExposureVariationJobs` | class | 4 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/ExposureVariationJobs.java:5` |
| `ExposureVariations` | class | 4 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/ExposureVariations.java:5` |
| `S3ConnectionManager` | class | 3 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/S3ConnectionManager.java:25` |
| `DataCatalogService` | class | 3 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/DataCatalogService.scala:30` |
| `RMSStorageWrapper` | interface | 2 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageWrapper.java:19` |
| `AccountManager` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/dao/AccountManager.java:14` |
| `S3SyncWrapper` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/impl/S3SyncWrapper.java:33` |
| `ArtifactDetails` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/model/RegisterPortfolioResponse.scala:52` |
| `PortfolioDetails` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/model/PortfolioDetails.scala:3` |
| `PrimaryKeyPathMap` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/model/RegisterPortfolioResponse.scala:72` |
| `TableBounds` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/model/TableBounds.scala:3` |
| `ExposureVariationsDetailsJson` | class | 2 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/ExposureVariationsDetailsJson.java:3` |
| `PortfolioManager` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/dao/PortfolioManager.java:11` |
| `TreatyManager` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/dao/TreatyManager.java:13` |
| `DataHelper` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/DataHelper.java:8` |
| `S3AsyncWrapper` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/impl/S3AsyncWrapper.java:58` |
| `SurrogateJobIdPathDetails` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/SurrogateJobIdPathDetails.java:5` |
| `AccountDetails` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/model/AccountDetails.scala:3` |
| `AccountService` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/services/AccountService.java:13` |
| `PortfolioService` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/services/PortfolioService.java:15` |
| `QueryEdmResult` | class | 1 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/QueryEdmResult.java:3` |
| `RMSStorageBuilder` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageBuilder.java:7` |
| `DataSourceErrorCode` | enum | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/datasource/DataSourceErrorCode.java:7` |
| `ReadWriteDataSource` | interface | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/db/ReadWriteDataSource.java:7` |
| `ReadWriteDataSourceImpl` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/db/ReadWriteDataSourceImpl.java:8` |
| `HelperFile` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/HelperFile.java:3` |
| `DatabaseBase` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/DatabaseBase.java:7` |
| `ManagedDatabase` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/ManagedDatabase.java:7` |
| `VariationJobDetails` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/model/VariationJobDetails.java:3` |
| `AsyncS3UploadDownloadIT` | class | 0 | `exposure-snapshot/snapshot-sdk/src/test/scala/com/rms/unifiedstore/sdk/AsyncS3UploadDownloadIT.scala:15` |
| `CatalogDetails` | class | 0 | `exposure-snapshot/snapshot-sdk/src/test/scala/com/rms/unifiedstore/sdk/DataCatalogServiceIT.scala:194` |
| `DataCatalogServiceIT` | class | 0 | `exposure-snapshot/snapshot-sdk/src/test/scala/com/rms/unifiedstore/sdk/DataCatalogServiceIT.scala:19` |
| `GetCatalogResponse` | class | 0 | `exposure-snapshot/snapshot-sdk/src/test/scala/com/rms/unifiedstore/sdk/DataCatalogServiceIT.scala:192` |
| `AccountDetailsResponse` | class | 0 | `exposure-snapshot/snapshot-sdk/src/main/scala/com/rms/unifiedstore/sdk/model/RegisterAccountDetails.scala:6` |

_32 more; use `cdp query module exposure-snapshot/snapshot-sdk`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-sdk/(files+2)` | 6 | 536 | structural only |
| `root/exposure-snapshot/snapshot-sdk/src/main/java` | 30 | 3,933 | structural only |
| `root/exposure-snapshot/snapshot-sdk/src/main/scala` | 14 | 3,463 | structural only |
