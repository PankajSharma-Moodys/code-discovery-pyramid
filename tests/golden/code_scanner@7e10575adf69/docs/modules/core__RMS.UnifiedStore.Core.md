# `core/RMS.UnifiedStore.Core`

78 tracked files, 2,855 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/core/RMS.UnifiedStore.Core/(Contracts+2)`, `root/core/RMS.UnifiedStore.Core/(files+7)`, `root/core/RMS.UnifiedStore.Core/Exceptions`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** `catalog-service/RMS.UnifiedStore.Service.Catalog` (207 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (95 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests` (12 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (44 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests` (22 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` (19 refs), `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` (19 refs), `core/RMS.UnifiedStore.Core.App` (21 refs), `core/RMS.UnifiedStore.Core.App.Tests` (5 refs), `core/RMS.UnifiedStore.Core.Tests` (11 refs), `service-api/RMS.UnifiedStore.Service.Api` (364 refs), `service-api/RMS.UnifiedStore.Service.Api.Common` (4 refs), `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests` (4 refs), `service-api/RMS.UnifiedStore.Service.Api.Tests` (157 refs), `tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB` (18 refs), `tests/performance/catalog-data-model/RMS.UnifiedStore.Tests.Performance.DataModel.DB.Tests` (2 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AccessException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/AccessException.cs:5` |
| `AccessViolationException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/AccessViolationException.cs:5` |
| `ApiInputException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/ApiInputException.cs:5` |
| `AppEntitlementResponse` | class | 0 | `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/Contracts/AppEntitlementResponse.cs:3` |
| `ArtifactNotFoundException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/ArtifactNotFoundException.cs:5` |
| `AuthServiceCache` | class | 0 | `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/AuthServiceClient.cs:301` |
| `AuthServiceClient` | class | 0 | `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/AuthServiceClient.cs:18` |
| `AuthServiceErrorException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/AuthServiceErrorException.cs:6` |
| `CallStackMetric` | class | 0 | `core/RMS.UnifiedStore.Core/Diagnostics/CallStackMetric.cs:11` |
| `CardUnavailableException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/CardUnavailableException.cs:6` |
| `CatalogDataConflictException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/CatalogDataConflictException.cs:5` |
| `CatalogDataNotFoundException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/CatalogDataNotFoundException.cs:5` |
| `CatalogSchemaNotFoundException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/CatalogSchemaNotFoundException.cs:5` |
| `ChainedConfigurationProvider` | class | 0 | `core/RMS.UnifiedStore.Core/Configuration/ChainedConfigurationProvider.cs:12` |
| `ConcurrentRequestConflictException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/ConcurrentRequestConflictException.cs:5` |
| `Constants` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:3` |
| `AppNames` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:80` |
| `Catalog` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:74` |
| `CatalogEntity` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:107` |
| `ContextItems` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:58` |
| `DefaultInstanceNames` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:68` |
| `Global` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:5` |
| `Header` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:17` |
| `MoveDatabaseJob` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:129` |
| `MoveExposureJob` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:119` |
| `Route` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:51` |
| `Securable` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:91` |
| `SecurableType` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:86` |
| `UserOnBehalfOf` | class | 0 | `core/RMS.UnifiedStore.Core/Constants.cs:63` |
| `CpuLogEnricher` | class | 0 | `core/RMS.UnifiedStore.Core/Logging/CpuLogEnricher.cs:11` |
| `CpuLogEnricherExtensions` | class | 0 | `core/RMS.UnifiedStore.Core/Logging/CpuLogEnricher.cs:76` |
| `DataConflictException` | class | 0 | `core/RMS.UnifiedStore.Core/Exceptions/DataConflictException.cs:5` |
| `DebuggableResponse` | class | 0 | `core/RMS.UnifiedStore.Core/Contracts/DebuggableResponse.cs:5` |
| `ErrorCode` | enum | 0 | `core/RMS.UnifiedStore.Core/Exceptions/ErrorCode.cs:3` |
| `ExceptionResponse` | class | 0 | `core/RMS.UnifiedStore.Core/Contracts/ExceptionResponse.cs:5` |
| `GaugeFactory` | class | 0 | `core/RMS.UnifiedStore.Core/Metric/GaugeFactory.cs:10` |
| `GroupDetailsResponse` | class | 0 | `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/Contracts/GroupDetailsResponse.cs:5` |
| `GroupGuidDetailsAdminDataResponse` | class | 0 | `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/Contracts/GroupDetailsResponse.cs:22` |
| `GroupGuidDetailsResponse` | class | 0 | `core/RMS.UnifiedStore.Core/Clients/ServiceManagement/Contracts/GroupDetailsResponse.cs:14` |
| `HashHelper` | class | 0 | `core/RMS.UnifiedStore.Core/Utils/HashHelper.cs:7` |

_62 more; use `cdp query module core/RMS.UnifiedStore.Core`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/core/RMS.UnifiedStore.Core/(Contracts+2)` | 10 | 179 | structural only |
| `root/core/RMS.UnifiedStore.Core/(files+7)` | 40 | 2,259 | structural only |
| `root/core/RMS.UnifiedStore.Core/Exceptions` | 28 | 417 | structural only |
