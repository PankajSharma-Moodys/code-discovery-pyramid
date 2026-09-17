# Unknowns — the tribal-knowledge inventory

Every question this run could not answer, with the anchor that raised it. This is the list to take to the incumbent team before they leave. A gap here is *output*, not failure: the alternative is a document that asserts a plausible answer, and a reader who cannot tell the difference.

> **Coverage: 0.0%** — 0 of 4728 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/(.github+3)`, `root/(build+5)`, `root/(files)`, `root/.claude`, `root/.cursor`, `root/automation`, `root/automation/api-automation/(files+10)`, `root/automation/api-automation/src/main/java/com/rms/uds/tests`.

## `root`

- **What contract does automation actually publish?**
  - _why unresolved:_ 42 of its 44 files are untracked and generated at build time, so its public surface cannot be read from the repository.
- **What contract does client-java actually publish?**
  - _why unresolved:_ 417 of its 420 files are untracked and generated at build time, so its public surface cannot be read from the repository.
- **What contract does exposure-snapshot/snapshot-legacy actually publish?**
  - _why unresolved:_ 57 of its 58 files are untracked and generated at build time, so its public surface cannot be read from the repository.
- **What contract does sql-pool actually publish?**
  - _why unresolved:_ 457 of its 477 files are untracked and generated at build time, so its public surface cannot be read from the repository.

## Public types with no static reference

No static reference found. Framework-managed entry points are excluded: dependency-injection annotations, HTTP resource registration, scheduled jobs, repositories, entities and generated mappers. These are candidates for review, not dead code (§6.6).

2672 candidate(s). These are **not** dead code; any of dependency injection, HTTP resource registration, job discovery or generated implementations makes a naive dead-code claim wrong.

- `AbstractJobHandler` `core/RMS.UnifiedStore.Core.App/Job/AbstractJobHandler.cs:8`
- `AbstractVerbGroup` `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/AbstractVerbGroup.cs:8`
- `AccessCheckTask` `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/AccessCheckTask.cs:11`
- `AccessControlContextData` `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ExecutionContext.cs:17`
- `AccessException` `core/RMS.UnifiedStore.Core/Exceptions/AccessException.cs:5`
- `AccessListHandler` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Handler/AccessListHandler.cs:22`
- `AccessScanTask` `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/AccessScanTask.cs:13`
- `AccessViolationException` `core/RMS.UnifiedStore.Core/Exceptions/AccessViolationException.cs:5`
- `AccumulationAnalysisHandler` `catalog-service/RMS.UnifiedStore.Service.Catalog/Handlers/Analysis/AccumulationAnalysisHandler.cs:9`
- `AddEdmException` `service-api/RMS.UnifiedStore.Service.Api/Exceptions/AddEdmException.cs:5`
- `AdminConnectionStringRequest` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminConnectionStringRequest.cs:5`
- `AdminConnectionStringResponse` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminConnectionStringResponse.cs:5`
- `AdminDataApiNegativeTest` `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests/AdminDataApiNegativeTest.cs:19`
- `AdminDataApiTest` `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests/AdminDataApiTest.cs:28`
- `AdminDataHandlerTests` `service-api/RMS.UnifiedStore.Service.Api.Tests/Handlers/AdminDataHandlerTests.cs:28`
- `AdminDataNegativeTestData` `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests/AdminDataNegativeTestData.cs:22`
- `AdminDataRequest` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/AdminDataRequest.cs:7`
- `AdminDataResponse` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/AdminDataResponse.cs:13`
- `AdminDatabaseRequest` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminDatabaseRequest.cs:7`
- `AdminDatabaseResponse` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminDatabaseResponse.cs:7`
- `AdminJobRequest` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminJobRequest.cs:7`
- `AdminJobResponse` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminJobResponse.cs:6`
- `AdminLoginRequest` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminLoginRequest.cs:3`
- `AdminLoginResponse` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminLoginResponse.cs:6`
- `AdminSqlInstanceRequest` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/Admin/AdminSqlInstanceRequest.cs:5`
- `AesStringEncryptionTests` `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Security/AesStringEncryptionTests.cs:8`
- `AlertNotReadyTenantBackgroundJob` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/BackgroundJobs/AlertNotReadyTenantBackgroundJob.cs:12`
- `AlertNotReadyTenantBackgroundJobTest` `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/BackgroundJobs/AlertNotReadyTenantJobTest.cs:15`
- `ApiInputException` `core/RMS.UnifiedStore.Core/Exceptions/ApiInputException.cs:5`
- `AppEntitlementResponse` `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/Contracts/AppEntitlementResponse.cs:3`
- `Archive` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/Archive.cs:11`
- `ArchiveAccess` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveAccess.cs:8`
- `ArchiveDatabaseRequest` `service-api/RMS.UnifiedStore.Service.Api/Contracts/v1/ArchiveDatabaseRequest.cs:11`
- `ArchiveDatabaseResult` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/ArchiveDatabaseResult.cs:3`
- `ArchiveDetail` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/Contracts/ArchivesDetail.cs:5`
- `ArchiveEdm` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveEdm.cs:9`
- `ArchiveEdmTests` `managed-sql/RMS.UnifiedStore.Service.ManagedSql.Tests/Integration/Archive/ArchiveEdmTest.cs:9`
- `ArchiveExtensions` `service-api/RMS.UnifiedStore.Service.Api/Integration/ArchiveExtensions.cs:10`
- `ArchiveNotFoundException` `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Exceptions/ArchiveNotFoundException.cs:6`
- `ArchiveRecord` `managed-sql/RMS.UnifiedStore.Service.ManagedSql/DataLayer/ArchiveRecord.cs:10`
