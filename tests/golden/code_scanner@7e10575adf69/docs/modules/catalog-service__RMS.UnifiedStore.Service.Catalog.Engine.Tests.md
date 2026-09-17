# `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests`

57 tracked files, 6,789 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/(files+3)`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (149 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (52 refs), `core/RMS.UnifiedStore.Core` (22 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ExpressionInterpreterTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/QueryV2/ExpressionInterpreterTests.cs:15` |
| `NormalizedParserTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/QueryV2/NormalizedParserTests.cs:12` |
| `ConditionalMapReduceExecutorTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Executor/ConditionalMapReduceExecutorTests.cs:19` |
| `SequentialExecutorTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Executor/SequentialExecutorTests.cs:19` |
| `CardDataQueryModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/CardDataQueryModuleTests.cs:18` |
| `CardDataTableQueryModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/CardDataTableQueryModuleTests.cs:16` |
| `CheckAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/CheckAccessModuleTests.cs:15` |
| `CheckArtifactAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/CheckArtifactAccessModuleTests.cs:15` |
| `CleanupSecurablesModulesTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/CleanupSecurablesModulesTests.cs:22` |
| `GetSecurableAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/GetSecurableAccessModuleTests.cs:25` |
| `PagingModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/PagingModuleTests.cs:13` |
| `ParallelModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/ParallelModuleTests.cs:13` |
| `QueryContextAggregatorModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/QueryContextAggregatorModuleTests.cs:13` |
| `QueryContextScanAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/QueryContextScanAccessModuleTests.cs:20` |
| `QueryContextSortModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/QueryContextSortModuleTests.cs:25` |
| `QueryPartitionCountReduceModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/QueryPartitionCountReduceModuleTests.cs:12` |
| `QueryPartitionReduceModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/QueryPartitionReduceModuleTests.cs:13` |
| `RegisterAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/RegisterAccessModuleTests.cs:20` |
| `RegisterArtifactModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/RegisterArtifactModuleTests.cs:19` |
| `RegisterCardModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/RegisterCardModuleTests.cs:21` |
| `RemoveAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/RemoveAccessModuleTests.cs:21` |
| `RemoveArtifactModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/RemoveArtifactModuleTests.cs:19` |
| `RemoveCardModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/RemoveCardModuleTests.cs:21` |
| `TransactionModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/TransactionModuleTests.cs:13` |
| `UpdateArtifactModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/UpdateArtifactModuleTests.cs:19` |
| `UpdateCardModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/UpdateCardModuleTests.cs:22` |
| `UpdateSecurableAccessModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/UpdateSecurableAccessModuleTests.cs:22` |
| `ValidateCardModuleTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module/ValidateCardModuleTests.cs:21` |
| `AccessCheckTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/AccessCheckTaskTests.cs:12` |
| `AccessScanTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/AccessScanTaskTests.cs:17` |
| `ArtifactAccessCheckTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/ArtifactAccessCheckTaskTests.cs:14` |
| `ArtifactRegisterTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/ArtifactRegisterTaskTests.cs:20` |
| `ArtifactRemoveTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/ArtifactRemoveTaskTests.cs:19` |
| `ArtifactUpdateTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/ArtifactUpdateTaskTests.cs:20` |
| `CardArtifactDataTableQueryTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/CardArtifactDataTableQueryTaskTests.cs:14` |
| `CardDataQueryTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/CardDataQueryTaskTests.cs:16` |
| `CardDataTableQueryTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/CardDataTableQueryTaskTests.cs:14` |
| `CardIdSortTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/CardIdSortTaskTests.cs:17` |
| `CardIndexDataQueryTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/CardIndexDataQueryTaskTests.cs:14` |
| `CardRegisterTaskTests` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks/CardRegisterTaskTests.cs:18` |

_16 more; use `cdp query module catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/(files+3)` | 11 | 2,161 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Module` | 24 | 3,039 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog.Engine.Tests/Execution/Tasks` | 22 | 1,589 | structural only |
