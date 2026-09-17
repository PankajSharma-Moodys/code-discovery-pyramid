# `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests`

108 tracked files, 31,246 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/(Archives+4)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/(BackgroundJobs+4)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/(files+10)`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Handler`, `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/SqlInstances`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `managed-sql/RMS.UnifiedStore.Service.ManagedSql` (343 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AesStringEncryptionTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Security/AesStringEncryptionTests.cs:8` |
| `AlertNotReadyTenantBackgroundJobTest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/BackgroundJobs/AlertNotReadyTenantJobTest.cs:15` |
| `ArchiveEdmTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Integration/Archive/ArchiveEdmTest.cs:9` |
| `ArchivesControllerPriorityTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Controllers/ArchivesControllerPriorityTests.cs:24` |
| `ArchivesHandlerTest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Archives/ArchivesHandlerTest.cs:37` |
| `ArchivesUtilTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Archives/ArchivesUtilTests.cs:7` |
| `CatalogDataServiceTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/Catalog/CatalogDataServiceTests.cs:21` |
| `CheckSqlInstancesReachableJobTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/BackgroundJobs/CheckSqlInstancesReachableJobTests.cs:22` |
| `CleanupEbsSnapshotsJobTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/BackgroundJobs/CleanupEbsSnapshotsJobTests.cs:19` |
| `CleanupFilesOnVolumesJobTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/BackgroundJobs/CleanupFilesOnVolumesJobTests.cs:18` |
| `ConnectionStringRepositoryTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/ConnectionStringRepositoryTests.cs:16` |
| `DatabaseAttachManagerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/DatabaseAttachManagerTests.cs:20` |
| `DatabaseDiskSpaceJobTest` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/BackgroundJobs/DatabaseDiskSpaceJobTest.cs:17` |
| `DatabaseExportHandlerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/DatabaseExportHandlerTests.cs:25` |
| `DatabaseHandlerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/DatabaseHandlerTests.cs:52` |
| `DatabaseImportHandlerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/DatabaseImportHandlerTests.cs:24` |
| `DatabaseInitializerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/SqlInstances/DatabaseInitializerTests.cs:19` |
| `DatabaseLifecycleTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/DatabaseLifecycleTests.cs:15` |
| `DatabaseMetadataHandlerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/DatabaseMetadataHandlerTests.cs:24` |
| `DatabaseRepositoryTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/DatabaseRepositoryTests.cs:18` |
| `DatabasesControllerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Controllers/DatabasesControllerTests.cs:18` |
| `EFBaseRepositoryTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/EFBaseRepositoryTests.cs:18` |
| `TestManagedSqlDbContext` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/EFBaseRepositoryTests.cs:217` |
| `FakeDatabaseRepository` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/FakeDatabaseRepository.cs:16` |
| `FakeTransientSqlInstanceRepository` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/DataLayer/FakeTransientSqlInstanceRepository.cs:12` |
| `ForceRestartHandlerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/SqlInstances/ForceRestartHandlerTests.cs:16` |
| `IFakeHttpMessageHandler` | interface | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Http/IFakeHttpMessageHandler.cs:7` |
| `IMeteringClientWithResponse` | interface | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Integration/MeteringApiIntegrationTests.cs:28` |
| `JobMetricWorkflowServiceTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Workflow/JobMetricWorkflowServiceTests.cs:15` |
| `JobMetricsControllerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Controllers/Internal/v1/JobMetricsControllerTests.cs:12` |
| `JobTypeTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Jobs/JobTypeTests.cs:8` |
| `JobsHandlerTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Jobs/JobsHandlerTests.cs:17` |
| `LoginHelperTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases/LoginHelperTests.cs:22` |
| `ManagedSqlClusterNameResolverTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/SqlInstances/ManagedSqlClusterNameResolverTests.cs:6` |
| `ManagedSqlInstanceContextTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/ManagedSqlInstanceContextTests.cs:16` |
| `MeteringApiIntegrationTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Integration/MeteringApiIntegrationTests.cs:35` |
| `OtherClass` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Engine/OtherClass.cs:3` |
| `PackageResolverTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/TenantProvisioning/PackageResolverTests.cs:8` |
| `PackageSettingsFactoryTests` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/TenantProvisioning/PackageSettingsFactoryTests.cs:11` |
| `Entry` | class | 0 | `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/TenantProvisioning/PackageSettingsFactoryTests.cs:115` |

_74 more; use `cdp query module managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/(Archives+4)` | 26 | 5,997 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/(BackgroundJobs+4)` | 26 | 5,976 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/(files+10)` | 25 | 3,796 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Databases` | 8 | 4,655 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Handler` | 13 | 6,795 | structural only |
| `root/managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/SqlInstances` | 10 | 4,027 | structural only |
