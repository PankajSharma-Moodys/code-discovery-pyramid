# `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`

103 tracked files, 9,068 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/(files+6)`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (159 refs), `core/RMS.UnifiedStore.Core` (44 refs), `core/RMS.UnifiedStore.Core.App` (1 refs)

**Imported by:** `catalog-service/RMS.UnifiedStore.Service.Catalog` (44 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests` (52 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` (1 refs), `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` (1 refs), `service-api/RMS.UnifiedStore.Service.Api` (5 refs), `service-api/RMS.UnifiedStore.Service.Api.Tests` (1 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AccessCheckTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/AccessCheckTask.cs:11` |
| `AccessControlContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ExecutionContext.cs:17` |
| `AccessScanTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/AccessScanTask.cs:13` |
| `ArtifactAccessCheckTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/ArtifactAccessCheckTask.cs:12` |
| `ArtifactQueryByIdTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/ArtifactQueryByIdTask.cs:13` |
| `ArtifactRegisterContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ArtifactRegisterContextData.cs:6` |
| `ArtifactRegisterTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/ArtifactRegisterTask.cs:15` |
| `ArtifactRemoveContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ArtifactRemoveContextData.cs:3` |
| `ArtifactRemoveTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/ArtifactRemoveTask.cs:15` |
| `ArtifactUpdateContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ArtifactUpdateContextData.cs:6` |
| `ArtifactUpdateTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/ArtifactUpdateTask.cs:15` |
| `BuilderData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/Builder/IBuilderData.cs:12` |
| `BuilderExtensions` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/Builder/BuilderExtensions.cs:6` |
| `CardArtifactDataTableQueryTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardArtifactDataTableQueryTask.cs:12` |
| `CardDataQueryModule` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/CardDataQueryModule.cs:15` |
| `CardDataQueryTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardDataQueryTask.cs:16` |
| `CardDataTableQueryModule` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/CardDataTableQueryModule.cs:13` |
| `CardDataTableQueryTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardDataTableQueryTask.cs:12` |
| `CardIdSortTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardIdSortTask.cs:14` |
| `CardIndexDataQueryTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardIndexDataQueryTask.cs:10` |
| `CardQueryContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CardQueryContextData.cs:6` |
| `CardQueryPartition` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CardQueryContextData.cs:26` |
| `CardRegisterContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CardRegisterContextData.cs:5` |
| `CardRemoveContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CardRemoveContextData.cs:6` |
| `CardRemoveTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardRemoveTask.cs:17` |
| `CardUpdateContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CardUpdateContextData.cs:6` |
| `CardUpdateTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CardUpdateTask.cs:17` |
| `CatalogStorageModule` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/CatalogStorageModule.cs:10` |
| `CatalogStorageTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/CatalogStorageTask.cs:9` |
| `CheckAccessContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CheckAccessContextData.cs:6` |
| `CheckAccessModule` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/CheckAccessModule.cs:12` |
| `CheckArtifactAccessContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CheckArtifactAccessContextData.cs:6` |
| `CheckArtifactAccessModule` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/CheckArtifactAccessModule.cs:12` |
| `CleanupSecurablesContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/CleanupSecurablesContextData.cs:8` |
| `ConditionalMapReduceContext` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ConditionalMapReduceContext.cs:5` |
| `ConditionalMapReduceExecutor` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Executor/ConditionalMapReduceExecutor.cs:11` |
| `ContextData` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ExecutionContext.cs:13` |
| `ContextQueryTask` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks/ContextQueryTask.cs:9` |
| `ExecutionContext` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Context/ExecutionContext.cs:7` |
| `GetSecurableAccessModule` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module/GetSecurableAccessModule.cs:19` |

_99 more; use `cdp query module catalog-service/RMS.UnifiedStore.Service.Catalog.Engine`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/(files+6)` | 39 | 5,025 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Module` | 34 | 2,140 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine/Execution/Tasks` | 30 | 1,903 | structural only |
