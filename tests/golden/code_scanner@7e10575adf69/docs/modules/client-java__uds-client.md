# `client-java/uds-client`

248 tracked files, 36,295 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/client-java/uds-client/(files+10)`, `root/client-java/uds-client/src/(helper+7)`, `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/(files)`, `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/(files)`, `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/analysis`, `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/(files)`, `root/client-java/uds-client/src/test/java/com/rms/unifiedstore/(files)`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (247 refs), `exposure-snapshot/ods-domain-data` (2 refs), `exposure-snapshot/snapshot-sdk` (2 refs)

**Imported by:** `client-java/uds-client-integration-tests` (170 refs), `exposure-snapshot/download-exposure` (1 refs), `exposure-snapshot/ods-domain-data` (1 refs), `exposure-snapshot/snapshot-api` (27 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` (6 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` (1 refs), `exposure-snapshot/snapshot-sdk` (11 refs), `exposure-snapshot/snapshot-task-create` (2 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `UdsDateDeserializer` | class | 24 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/converter/UdsDateDeserializer.java:12` |
| `SortOrder` | enum | 24 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/SortOrder.java:3` |
| `UdsDateSerializer` | class | 21 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/converter/UdsDateSerializer.java:10` |
| `UnifiedStoreClient` | interface | 17 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClient.java:20` |
| `GetCatalogCardResponse` | class | 17 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/GetCatalogCardResponse.java:10` |
| `UnifiedStoreClientFactory` | class | 16 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientFactory.java:5` |
| `CreateConnectionStringResponse` | class | 16 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/CreateConnectionStringResponse.java:16` |
| `UdsServerType` | enum | 14 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/UdsServerType.java:6` |
| `ExposureBundleEntity` | class | 14 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/exposurebundle/ExposureBundleEntity.java:16` |
| `ExposureBundleTableSetEntity` | class | 13 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/exposurebundle/ExposureBundleTableSetEntity.java:13` |
| `CatalogCards` | class | 12 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/CatalogCards.java:3` |
| `RiskAnalysisEntity` | class | 12 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/analysis/RiskAnalysisEntity.java:16` |
| `SecurableDetails` | class | 9 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/SecurableDetails.java:5` |
| `ServerType` | enum | 8 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/ServerType.java:3` |
| `SqlInstanceDetails` | class | 8 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/sqlinstances/SqlInstanceDetails.java:8` |
| `CreateEdmRequestv2` | class | 7 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/CreateEdmRequestv2.java:8` |
| `ExposureBundleMetricEntity` | class | 7 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/exposurebundle/ExposureBundleMetricEntity.java:12` |
| `TableSetType` | enum | 7 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/exposurebundle/TableSetType.java:3` |
| `PatchExposureSetRequestV2` | class | 7 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/exposureset/PatchExposureSetRequestV2.java:5` |
| `InstanceType` | enum | 7 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/sqlinstances/InstanceType.java:3` |
| `ConverterUtility` | class | 6 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/converter/ConverterUtility.java:11` |
| `EdmEntity` | class | 6 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/EdmEntity.java:16` |
| `CreateExposureSetRequest` | class | 6 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/exposureset/CreateExposureSetRequest.java:8` |
| `PatchCardRequest` | class | 6 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/securable/PatchCardRequest.java:5` |
| `DataVersion` | enum | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/enums/DataVersion.java:7` |
| `DatasourceHelper` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/helper/DatasourceHelper.java:10` |
| `ArchiveDatabaseRequest` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/archive/ArchiveDatabaseRequest.java:7` |
| `RegisterCardRequest` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/RegisterCardRequest.java:8` |
| `Analysis` | interface | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/analysis/Analysis.java:3` |
| `GenericAnalysisDetails` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/analysis/GenericAnalysisDetails.java:16` |
| `RiskAnalysisDetails` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/analysis/RiskAnalysisDetails.java:16` |
| `BaseCreateTransientDbRequest` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/base/BaseCreateTransientDbRequest.java:10` |
| `KmsKeyResponse` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/kmskey/KmsKeyResponse.java:7` |
| `KmsKeyStatus` | enum | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/kmskey/KmsKeyStatus.java:5` |
| `CreateLoss` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/loss/CreateLoss.java:9` |
| `ArchiveDatabasesFromSnapshotInput` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/model/sqlinstances/ArchiveDatabasesFromSnapshotInput.java:8` |
| `ServerConnectionStringResponse` | class | 5 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/server/ServerConnectionStringResponse.java:3` |
| `CatalogService` | interface | 4 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/CatalogService.java:12` |
| `CatalogServiceFactory` | class | 4 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/CatalogServiceFactory.java:8` |
| `ResultRegisterService` | interface | 4 | `client-java/uds-client/src/main/java/com/rms/unifiedstore/ResultRegisterService.java:12` |

_185 more; use `cdp query module client-java/uds-client`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/client-java/uds-client/(files+10)` | 29 | 1,018 | structural only |
| `root/client-java/uds-client/src/(helper+7)` | 40 | 3,888 | structural only |
| `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/(files)` | 70 | 15,458 | structural only |
| `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/(files)` | 41 | 2,469 | structural only |
| `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/model/catalog/analysis` | 13 | 4,333 | structural only |
| `root/client-java/uds-client/src/main/java/com/rms/unifiedstore/model/database/(files)` | 39 | 2,629 | structural only |
| `root/client-java/uds-client/src/test/java/com/rms/unifiedstore/(files)` | 16 | 6,500 | structural only |
