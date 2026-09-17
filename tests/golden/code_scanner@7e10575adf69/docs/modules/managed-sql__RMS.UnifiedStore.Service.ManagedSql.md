# `managed-sql/RMS.UnifiedStore.Service.ManagedSql`

518 tracked files, 73,362 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(App+4)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(Aws+4)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(BackgroundJobs+5)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(Clusters+6)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(EdmSync+5)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(files+1)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/(files)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/(files)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/(files)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Handlers/(files)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests` (343 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `TransientSqlInstanceHandler` | class | 1 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/OnDemand/TransientSqlInstanceHandler.cs:34` |
| `AddActualTimesToMaintenanceSchedules` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20260820185037_AddActualTimesToMaintenanceSchedules.cs:9` |
| `AddArchive` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20230329185727_AddArchive.cs:8` |
| `AddCallbackIdIndex` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20240920221138_AddCallbackIdIndex.cs:8` |
| `AddImportJobId` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20220322230626_AddImportJobId.cs:7` |
| `AddIsMigrating` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20230308233816_AddIsMigrating.cs:7` |
| `AddJobType` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20230614173213_AddJobType.cs:7` |
| `AddLastUsed` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20220420161339_AddLastUsed.cs:8` |
| `AddMaintenanceTables` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20260313204003_AddMaintenanceTables.cs:9` |
| `AddPackageName` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20210812223513_AddPackageName.cs:5` |
| `AddQuotaTables` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20250910232230_AddQuotaTables.cs:9` |
| `AddReserveAndReleaseJobStoredProc` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20250910232908_AddReserveAndReleaseJobStoredProc.cs:8` |
| `AddSpaceDetails` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20251111212218_AddSpaceDetails.cs:9` |
| `AddStorageTypeId` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20241105142449_AddStorageTypeId.cs:8` |
| `AddSubmittedAsToJobRecord` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20240124161538_AddSubmittedAsToJobRecord.cs:7` |
| `AddWorkflowCallbacksRetentionIndexes` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations/20260625190704_AddWorkflowCallbacksRetentionIndexes.cs:8` |
| `AdminConnectionStringRequest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminConnectionStringRequest.cs:5` |
| `AdminConnectionStringResponse` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminConnectionStringResponse.cs:5` |
| `AdminController` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/AdminController.ConnectionString.cs:13` |
| `AdminDatabaseRequest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminDatabaseRequest.cs:7` |
| `AdminDatabaseResponse` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminDatabaseResponse.cs:7` |
| `AdminJobRequest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminJobRequest.cs:7` |
| `AdminJobResponse` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminJobResponse.cs:6` |
| `AdminLoginRequest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminLoginRequest.cs:3` |
| `AdminLoginResponse` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminLoginResponse.cs:6` |
| `AdminSqlInstanceRequest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminSqlInstanceRequest.cs:5` |
| `AlertNotReadyTenantBackgroundJob` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/BackgroundJobs/AlertNotReadyTenantBackgroundJob.cs:12` |
| `AppEntitlementResponse` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/TenantProvisioning/Http/Contracts/AppEntitlementResponse.cs:3` |
| `Archive` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/Archive.cs:8` |
| `ArchiveAccess` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/ArchiveAccess.cs:7` |
| `ArchiveDatabaseResult` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/ArchiveDatabaseResult.cs:3` |
| `ArchiveDetail` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/ArchivesDetail.cs:5` |
| `ArchiveEdm` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Integration/Archive/ArchiveEdm.cs:7` |
| `ArchiveNotFoundException` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Exceptions/ArchiveNotFoundException.cs:6` |
| `ArchiveRecord` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/ArchiveRecord.cs:10` |
| `ArchivesController` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1/ArchivesController.cs:25` |
| `ArchivesDatabaseResult` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/ArchivesDatabaseResult.cs:3` |
| `ArchivesHandler` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Archives/ArchivesHandler.cs:31` |
| `ArchivesResponse` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/ArchivesResponse.cs:5` |
| `ArtifactResolverExtensions` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Extensions/ArtifactResolverExtensions.cs:10` |

_486 more; use `cdp query module managed-sql/RMS.UnifiedStore.Service.ManagedSql`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(App+4)` | 40 | 6,000 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(Aws+4)` | 39 | 891 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(BackgroundJobs+5)` | 37 | 5,995 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(Clusters+6)` | 40 | 3,413 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(EdmSync+5)` | 35 | 5,999 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/(files+1)` | 7 | 215 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/(files)` | 104 | 1,795 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Controllers/v1` | 28 | 8,168 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/(files)` | 35 | 1,260 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/(files)` | 20 | 4,640 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/EF/Migrations` | 51 | 18,516 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Databases` | 22 | 4,947 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/Handlers/(files)` | 28 | 6,019 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql/SqlInstances` | 32 | 5,504 | structural only |
