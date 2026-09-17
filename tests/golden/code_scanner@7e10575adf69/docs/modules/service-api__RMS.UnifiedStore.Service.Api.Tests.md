# `service-api/RMS.UnifiedStore.Service.Api.Tests`

162 tracked files, 51,363 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(Api.Clients.ResourceManager+13)`, `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(Common+4)`, `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(Engine+3)`, `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(files)`, `root/service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/(files)`, `root/service-api/RMS.UnifiedStore.Service.Api.Tests/RecurringJobs`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (149 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (1 refs), `core/RMS.UnifiedStore.Core` (157 refs), `core/RMS.UnifiedStore.Core.App` (15 refs), `service-api/RMS.UnifiedStore.Service.Api` (556 refs), `service-api/RMS.UnifiedStore.Service.Api.Common` (3 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AdminDataHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/AdminDataHandlerTests.cs:28` |
| `ArchiveSecurableRequestTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/ArchiveSecurableRequestTests.cs:9` |
| `ArchivesMetricsReportAndCleanupJobTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/RecurringJobs/ArchivesMetricsReportAndCleanupJobTests.cs:26` |
| `AutoPurgeNotificationJobTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/RecurringJobs/AutoPurgeNotificationJobTests.cs:24` |
| `CatalogQueryTransformerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Utils/CatalogQueryTransformerTests.cs:10` |
| `CatalogServiceTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Integration/CatalogServiceTests.cs:25` |
| `CleanupExpiredSnapshotLeasesRecurringJobTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/RecurringJobs/CleanupExpiredSnapshotLeasesRecurringJobTests.cs:19` |
| `CreateEdmTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/CreateEdmTests.cs:28` |
| `CreateEdmv2Tests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/CreateEdmTestsv2.cs:28` |
| `CreateSnapshotHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Snapshots/CreateSnapshotHandlerTests.cs:14` |
| `CreateSnapshotLeaseHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Snapshots/CreateSnapshotLeaseHandlerTests.cs:15` |
| `CustomRoleHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/CustomRoleHandlerTests.cs:14` |
| `DataBridgeNotificationHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DataBridgeNotificationTests.cs:22` |
| `DatabaseAdminDataHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/DatabaseAdminDataHandlerTests.cs:41` |
| `DatabaseConnectorTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Utils/DatabaseConnectorTests.cs:11` |
| `DatabaseLockRepositoryTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DataLayer/EF/DatabaseLockRepositoryTests.cs:15` |
| `DatabridgeDatabaseQueryHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/DatabridgeDatabaseQueryHandlerTests.cs:17` |
| `DeleteSnapshotLeaseHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Snapshots/DeleteSnapshotLeaseHandlerTests.cs:11` |
| `DeregisterDataBridgeDatabaseHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DeregisterDataBridgeDatabaseHandlerTests.cs:19` |
| `DropArchivesTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DropArchivesTests.cs:18` |
| `DropDatabaseTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DropDatabaseTests.cs:25` |
| `DropDatabaseTestsv2` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DropDatabaseTestsv2.cs:25` |
| `DropTransientDbTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DropTransientDbTests.cs:20` |
| `DropTransientDbTestsv2` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DropTransientDbTestsv2.cs:20` |
| `EdmConnectionStringTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/EdmConnectionStringTests.cs:23` |
| `EdmMaintenanceHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/EdmMaintenance/EdmMaintenanceHandlerTests.cs:19` |
| `ExportEdmTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/ExportEdmTests.cs:20` |
| `ExposureDatabaseInitialPreparationHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/ExposureDatabaseInitialPreparationHandlerTests.cs:26` |
| `FakeRetryHandler` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Utils/FakeRetryHandler.cs:7` |
| `FakeServiceApiDbContext` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/DataLayer/EF/FakeServiceApiDbContext.cs:9` |
| `FilterValidatorTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Utils/FilterValidatorTests.cs:10` |
| `FlywayExceptionTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/FlyWayExceptionTests.cs:6` |
| `FlywayVersionTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/SchemaUpgrade/Flyway/FlywayVersionTests.cs:6` |
| `GetArchivesTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/GetArchivesTests.cs:19` |
| `GetDataBridgeDatabaseHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/GetDataBridgeDatabaseHandlerTests.cs:28` |
| `GetDataBridgeEdmHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/GetDataBridgeEdmHandlerTests.cs:18` |
| `GetSnapshotLeaseHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Snapshots/GetSnapshotLeaseHandlerTests.cs:14` |
| `GetTransientDbCountTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/GetTransientDbCountTests.cs:15` |
| `GroupNamesHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/GroupNamesHandlerTests.cs:20` |
| `GroupTranslationHandlerTests` | class | 0 | `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/GroupTranslationHandlerTests.cs:16` |

_123 more; use `cdp query module service-api/RMS.UnifiedStore.Service.Api.Tests`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(Api.Clients.ResourceManager+13)` | 26 | 4,233 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(Common+4)` | 14 | 5,992 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(Engine+3)` | 30 | 5,959 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api.Tests/(files)` | 46 | 17,299 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/(files)` | 27 | 11,240 | structural only |
| `root/service-api/RMS.UnifiedStore.Service.Api.Tests/RecurringJobs` | 19 | 6,640 | structural only |
