# `exposure-snapshot/entity-variation-task`

164 tracked files, 16,916 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/entity-variation-task/(files+8)`, `root/exposure-snapshot/entity-variation-task/src/(files+3)`, `root/exposure-snapshot/entity-variation-task/src/main/(constants+9)`, `root/exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors`, `root/exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/(files)`, `root/exposure-snapshot/entity-variation-task/src/test/java/com/rms/unifiedstore/entityvariation/helper`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ExposureSnapshotException` | class | 19 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/ExposureSnapshotException.java:3` |
| `EnvironmentConfigurationProvider` | class | 16 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/providers/EnvironmentConfigurationProvider.java:11` |
| `ExposureResponse` | class | 13 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/exposurebundle/ExposureResponse.java:22` |
| `PortfolioVariationIdMapping` | class | 10 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/PortfolioVariationIdMapping.java:12` |
| `LambdaSnapshotEdmBundleRequest` | class | 10 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/exposurebundle/LambdaSnapshotEdmBundleRequest.java:17` |
| `ExposureBundleS3JsonReader` | class | 8 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/service/exposurebundle/ExposureBundleS3JsonReader.java:21` |
| `ExposureBundleService` | class | 8 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/service/exposurebundle/ExposureBundleService.java:28` |
| `PortfolioSnapshotEngineInput` | class | 7 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/PortfolioSnapshotEngineInput.java:11` |
| `LambdaSnapshotEdmBundleStatusResponse` | class | 7 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/exposurebundle/LambdaSnapshotEdmBundleStatusResponse.java:15` |
| `GeoHazRequest` | class | 7 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/geohaz/request/GeoHazRequest.java:10` |
| `ExposureBundleErrorCode` | enum | 6 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/ExposureBundleErrorCode.java:5` |
| `WorkflowErrorCode` | enum | 6 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/WorkflowErrorCode.java:5` |
| `Result` | class | 6 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/EntityVariationOutput.java:20` |
| `PortfolioDetailsResponse` | class | 6 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/uds/PortfolioDetailsResponse.java:15` |
| `WorkflowExecution` | class | 6 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/workflow/WorkflowExecution.java:14` |
| `CoreConstants` | class | 5 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/constants/CoreConstants.java:3` |
| `WorkflowStatus` | enum | 5 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/constants/WorkflowStatus.java:3` |
| `ConfigurationErrorCode` | enum | 5 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/ConfigurationErrorCode.java:5` |
| `BundleRoot` | class | 5 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/exposurebundle/BundleRoot.java:16` |
| `DaoErrorCode` | enum | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/DaoErrorCode.java:5` |
| `DomainDataHttpClientException` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/DomainDataHttpClientException.java:3` |
| `ExposureBundleException` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/ExposureBundleException.java:3` |
| `PostProcessorErrorCode` | enum | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/PostProcessorErrorCode.java:5` |
| `UdsErrorCode` | enum | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/UdsErrorCode.java:5` |
| `PortfolioSnapshotEngineHelper` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/PortfolioSnapshotEngineHelper.java:95` |
| `CedantsReader` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/parquet/CedantsReader.java:8` |
| `DomainDataDownloader` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/parquet/DomainDataDownloader.java:19` |
| `LobDetReader` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/parquet/LobDetReader.java:14` |
| `AccountSnapshotEngineInput` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/AccountSnapshotEngineInput.java:11` |
| `VariationInfo` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/EntityVariationOutput.java:35` |
| `RegistrationData` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/RegistrationData.java:14` |
| `GeoHazLogResponse` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/geohaz/response/GeoHazLogResponse.java:10` |
| `FailsafeUtil` | class | 4 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/utils/FailsafeUtil.java:22` |
| `GeocodingErrorCode` | enum | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors/GeocodingErrorCode.java:5` |
| `PortfolioProcessor` | class | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/PortfolioProcessor.java:62` |
| `DomainDataImporter` | class | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/parquet/DomainDataImporter.java:12` |
| `S3FileDownloader` | class | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/s3/S3FileDownloader.java:17` |
| `AccountVariationIdMapping` | class | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/AccountVariationIdMapping.java:10` |
| `DataLoadingInput` | class | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/DataLoadingInput.java:13` |
| `EntityVariationOutput` | class | 3 | `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/model/EntityVariationOutput.java:13` |

_117 more; use `cdp query module exposure-snapshot/entity-variation-task`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/entity-variation-task/(files+8)` | 39 | 5,983 | structural only |
| `root/exposure-snapshot/entity-variation-task/src/(files+3)` | 40 | 1,080 | structural only |
| `root/exposure-snapshot/entity-variation-task/src/main/(constants+9)` | 39 | 1,315 | structural only |
| `root/exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/errors` | 24 | 703 | structural only |
| `root/exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/(files)` | 11 | 4,210 | structural only |
| `root/exposure-snapshot/entity-variation-task/src/test/java/com/rms/unifiedstore/entityvariation/helper` | 11 | 3,625 | structural only |
