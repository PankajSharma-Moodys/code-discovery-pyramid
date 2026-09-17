# `service-api/RMS.UnifiedStore.Service.Api`

1047 tracked files, 615,149 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/service-api/RMS.UnifiedStore.Service.Api/(App+5)`, `root/service-api/RMS.UnifiedStore.Service.Api/(Attribute+12)`, `root/service-api/RMS.UnifiedStore.Service.Api/(DataBridge+5)`, `root/service-api/RMS.UnifiedStore.Service.Api/(ExposureSnapshot+5)`, `root/service-api/RMS.UnifiedStore.Service.Api/(Internal+3)`, `root/service-api/RMS.UnifiedStore.Service.Api/(MoveDatabase+4)`, `root/service-api/RMS.UnifiedStore.Service.Api/(files+7)`, `root/service-api/RMS.UnifiedStore.Service.Api/(files+9)`, `root/service-api/RMS.UnifiedStore.Service.Api/Clients/ManagedSql`, `root/service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/(files)`, `root/service-api/RMS.UnifiedStore.Service.Api/Controllers/v1`, `root/service-api/RMS.UnifiedStore.Service.Api/DataLayer/(files)`, `root/service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations`, `root/service-api/RMS.UnifiedStore.Service.Api/DataMigration`, `root/service-api/RMS.UnifiedStore.Service.Api/Exceptions`, `root/service-api/RMS.UnifiedStore.Service.Api/Handlers/(files)`, `root/service-api/RMS.UnifiedStore.Service.Api/Integration`, `root/service-api/RMS.UnifiedStore.Service.Api/RecurringJobs`, `root/service-api/RMS.UnifiedStore.Service.Api/Resources/RollbackScripts`, `root/service-api/RMS.UnifiedStore.Service.Api/Resources/edm-init/sql`, `root/service-api/RMS.UnifiedStore.Service.Api/Resources/edm-upgrade/sql`, `root/service-api/RMS.UnifiedStore.Service.Api/Resources/upgrade-lookup/sql`, `root/service-api/RMS.UnifiedStore.Service.Api/Utils`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (272 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (5 refs), `core/RMS.UnifiedStore.Core` (364 refs), `core/RMS.UnifiedStore.Core.App` (55 refs), `service-api/RMS.UnifiedStore.Service.Api.Common` (6 refs)

**Imported by:** `service-api/RMS.UnifiedStore.Service.Api.Tests` (556 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `DatabaseSchema` | enum | 17 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/DatabaseSchema.cs:3` |
| `ExportDatabaseRequest` | class | 7 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/ExportDatabaseRequest.cs:5` |
| `ServerVersion` | enum | 7 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/ServerVersion.cs:3` |
| `JobErrorCode` | enum | 4 | `service-api/RMS.UnifiedStore.Service.Api/Exceptions/JobErrorCode.cs:3` |
| `ImportFromType` | enum | 2 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/ImportFromType.cs:3` |
| `ServerType` | enum | 2 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/ServerType.cs:7` |
| `DataVaultJobDetail` | class | 1 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/Internal/DataVaultUpgradeRequest.cs:6` |
| `CreateTransientDbRequest` | class | 1 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/CreateTransientDbRequest.cs:7` |
| `DataVersion` | enum | 1 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/DataVersion.cs:7` |
| `ExportDatabaseRequest` | class | 1 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/ExportDatabaseRequest.cs:3` |
| `ImportFromType` | enum | 1 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/ImportFromType.cs:3` |
| `ImportTransientDbRequest` | class | 1 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v3/ImportTransientDbRequest.cs:7` |
| `IdempotencyHelper` | class | 1 | `service-api/RMS.UnifiedStore.Service.Api/Handlers/IdempotencyHelper.cs:8` |
| `AddArchiveSize` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20241029142855_AddArchiveSize.cs:8` |
| `AddDataVaultSetting` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20250313225754_AddDataVaultSetting.cs:9` |
| `AddDatabaseHostingService` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20210512204303_AddDatabaseHostingService.cs:5` |
| `AddDatabaseName` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20210524170243_AddDatabaseName.cs:5` |
| `AddEdmException` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Exceptions/AddEdmException.cs:5` |
| `AddExposureVariationsv1` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220223192152_AddExposureVariationsv1.cs:6` |
| `AddJobAndRequestId` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220426222059_AddJobAndRequestId.cs:7` |
| `AddJobType` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20231213230641_AddJobType.cs:7` |
| `AddKmsInfoRecord` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20241121111623_AddKmsInfoRecord.cs:9` |
| `AddOnDemandLeaseId` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220613213301_AddOnDemandLeaseId.cs:7` |
| `AddPoolReservationIdColumnToTransientDb` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20221116183211_AddPoolReservationIdColumnToTransientDb.cs:7` |
| `AddSizeInMbToSnapshot` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220323231757_AddSizeInMbToSnapshot.cs:7` |
| `AddSubmittedAsToJobRecord` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20240124163902_AddSubmittedAsToJobRecord.cs:7` |
| `AddTenantQueues` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20250912181412_AddTenantQueues.cs:8` |
| `AddUdsRdsField` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20210907220317_AddUdsRdsField.cs:5` |
| `AdminDataController` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/AdminDataController.cs:35` |
| `AlterExposureVariationsv1` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220224162936_AlterExposureVariationsv1.cs:5` |
| `AlterExposureVariationsv2` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220308230924_AlterExposureVariationsv2.cs:7` |
| `AlterExposureVariationsv3` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220319000702_AlterExposureVariationsv3.cs:7` |
| `AlterExposureVariationsv4` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations/20220421171543_AlterExposureVariationsv4.cs:7` |
| `ArchiveDatabaseRequest` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/ArchiveDatabaseRequest.cs:11` |
| `ArchiveExtensions` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Integration/ArchiveExtensions.cs:10` |
| `ArchiveSecurableRequest` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/ArchiveSecurableRequest.cs:7` |
| `ArchivesController` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Controllers/v1/ArchivesController.cs:27` |
| `ArchivesMetricsReportAndCleanupJob` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/RecurringJobs/ArchivesMetricsReportAndCleanupJob.cs:39` |
| `AutoPurgeNotificationJob` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/RecurringJobs/AutoPurgeNotificationJob.cs:33` |
| `BackgroundJobRetryAttribute` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api/Attribute/BackgroundJobRetryAttribute.cs:9` |

_671 more; use `cdp query module service-api/RMS.UnifiedStore.Service.Api`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/service-api/RMS.UnifiedStore.Service.Api/(App+5)` | 40 | 4,959 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(Attribute+12)` | 40 | 1,543 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(DataBridge+5)` | 40 | 2,140 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(ExposureSnapshot+5)` | 40 | 1,670 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(Internal+3)` | 40 | 4,907 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(MoveDatabase+4)` | 37 | 5,999 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(files+7)` | 40 | 4,680 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/(files+9)` | 10 | 41 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Clients/ManagedSql` | 22 | 622 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/(files)` | 57 | 1,432 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Controllers/v1` | 20 | 4,127 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/DataLayer/(files)` | 36 | 3,794 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/DataLayer/EF/Migrations` | 53 | 11,632 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/DataMigration` | 27 | 1,714 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Exceptions` | 27 | 396 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Handlers/(files)` | 121 | 18,947 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Integration` | 16 | 5,029 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/RecurringJobs` | 29 | 5,881 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Resources/RollbackScripts` | 6 | 54,386 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Resources/edm-init/sql` | 2 | 77,253 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Resources/edm-upgrade/sql` | 291 | 358,664 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Resources/upgrade-lookup/sql` | 25 | 43,068 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api/Utils` | 28 | 2,265 | structural only |
