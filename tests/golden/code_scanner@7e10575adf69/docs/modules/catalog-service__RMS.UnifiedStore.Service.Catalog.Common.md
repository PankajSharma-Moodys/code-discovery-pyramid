# `catalog-service/RMS.UnifiedStore.Service.Catalog.Common`

375 tracked files, 41,806 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/(Cache+10)`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/(files+3)`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/(files)`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Handler`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Resources`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/db/migrations`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `core/RMS.UnifiedStore.Core` (95 refs), `core/RMS.UnifiedStore.Core.App` (15 refs)

**Imported by:** `catalog-service/RMS.UnifiedStore.Service.Catalog` (198 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Common.Tests` (113 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (159 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests` (149 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` (37 refs), `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` (42 refs), `service-api/RMS.UnifiedStore.Service.Api` (272 refs), `service-api/RMS.UnifiedStore.Service.Api.Common` (4 refs), `service-api/RMS.UnifiedStore.Service.Api.Integration.Tests` (7 refs), `service-api/RMS.UnifiedStore.Service.Api.Tests` (149 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `StringExtensions` | class | 4 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Extensions/StringExtensions.cs:6` |
| `Operation` | enum | 3 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/Operation.cs:3` |
| `TargetProperty` | enum | 3 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/TargetProperty.cs:3` |
| `Edm` | class | 2 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/Edm.cs:13` |
| `SqlPoolReservationStatus` | enum | 1 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/SqlPool/SqlPoolReservationStatus.cs:5` |
| `AccessListHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Handler/AccessListHandler.cs:22` |
| `AdminDataRequest` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/AdminDataRequest.cs:7` |
| `AdminDataResponse` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/AdminDataResponse.cs:13` |
| `Archive` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/Archive.cs:11` |
| `ArchiveAccess` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveAccess.cs:8` |
| `ArchiveEdm` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveEdm.cs:9` |
| `ArchiveNotFoundException` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Exceptions/ArchiveNotFoundException.cs:6` |
| `ArchiveResponse` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/v1/ArchiveResponse.cs:6` |
| `ArchiveResponse` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration/ArchiveResponse.cs:5` |
| `BooleanDataType` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/DataType/BooleanDataType.cs:5` |
| `BulkAction` | enum | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/BulkRequest.cs:14` |
| `BulkRequest` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/BulkRequest.cs:6` |
| `BulkResponse` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/BulkResponse.cs:8` |
| `BulkResult` | enum | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/BulkResponse.cs:20` |
| `CardQueryGroupsHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Handler/CardQueryGroupsHandler.cs:19` |
| `CatalogArtifactRow` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogArtifactRow.cs:3` |
| `CatalogArtifactTableSchema` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogArtifactTableSchema.cs:6` |
| `CatalogCardRow` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogCardRow.cs:3` |
| `CatalogCardTableSchema` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogCardTableSchema.cs:6` |
| `CatalogColumn` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogColumn.cs:5` |
| `CatalogDataModelVersion` | enum | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogDataModelVersion.cs:6` |
| `CatalogDataRow` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogDataRow.cs:5` |
| `CatalogDataType` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/DataType/CatalogDataType.cs:6` |
| `CatalogDataTypeConverter` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/DataType/CatalogDataTypeConverter.cs:7` |
| `CatalogDatabaseEntry` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Configuration/Entry/CatalogDatabaseEntry.cs:12` |
| `CatalogDatabaseType` | enum | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Storage/ICatalogDatabaseStorage.cs:7` |
| `CatalogEntity` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogEntity.cs:12` |
| `CatalogFilteredIndex` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogFilteredIndex.cs:5` |
| `CatalogGroupAccessTableSchema` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogGroupAccessTableSchema.cs:6` |
| `CatalogIndex` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogIndex.cs:5` |
| `CatalogIndexRange` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogIndexRange.cs:6` |
| `CatalogIndexRow` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data/CatalogIndexRow.cs:3` |
| `CatalogIndexTableSchema` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogIndexTableSchema.cs:12` |
| `CatalogMetadataVersion` | enum | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogMetadataVersion.cs:6` |
| `CatalogOwnerAccessTableSchema` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema/CatalogOwnerAccessTableSchema.cs:6` |

_253 more; use `cdp query module catalog-service/RMS.UnifiedStore.Service.Catalog.Common`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/(Cache+10)` | 40 | 1,332 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/(files+3)` | 40 | 3,736 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Contracts/(files)` | 63 | 1,169 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Data` | 31 | 1,185 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Handler` | 23 | 2,792 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Integration` | 21 | 6,553 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Resources` | 34 | 16,908 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/Schema` | 40 | 2,120 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Common/db/migrations` | 83 | 6,011 | structural only |
