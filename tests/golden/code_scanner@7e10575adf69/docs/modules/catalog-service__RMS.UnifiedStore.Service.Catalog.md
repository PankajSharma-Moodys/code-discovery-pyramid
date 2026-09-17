# `catalog-service/RMS.UnifiedStore.Service.Catalog`

115 tracked files, 11,133 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/catalog-service/RMS.UnifiedStore.Service.Catalog/(files+4)`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers`, `root/catalog-service/RMS.UnifiedStore.Service.Catalog/Job`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (198 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (44 refs), `core/RMS.UnifiedStore.Core` (207 refs), `core/RMS.UnifiedStore.Core.App` (12 refs)

**Imported by:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` (16 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AccessController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/AccessController.cs:22` |
| `AccessController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/AccessController.cs:24` |
| `AccessController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/v1/AccessController.cs:21` |
| `AccumulationAnalysisHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Handlers/Analysis/AccumulationAnalysisHandler.cs:9` |
| `AdminController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.Securable.cs:14` |
| `AdminController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/AdminController.cs:21` |
| `ArtifactBulkDeleteJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactBulkDeleteJob.cs:9` |
| `ArtifactBulkDeleteJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactBulkDeleteJobHandler.cs:15` |
| `ArtifactBulkRegisterJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactBulkRegisterJob.cs:9` |
| `ArtifactBulkRegisterJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactBulkRegisterJobHandler.cs:19` |
| `ArtifactBulkUpdateJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactBulkUpdateJob.cs:9` |
| `ArtifactBulkUpdateJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactBulkUpdateJobHandler.cs:19` |
| `ArtifactDeleteJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactDeleteJob.cs:8` |
| `ArtifactDeleteJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactDeleteJobHandler.cs:15` |
| `ArtifactRegisterJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactRegisterJob.cs:8` |
| `ArtifactRegisterJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactRegisterJobHandler.cs:19` |
| `ArtifactUpdateJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactUpdateJob.cs:8` |
| `ArtifactUpdateJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/ArtifactUpdateJobHandler.cs:19` |
| `Bootstrap` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Bootstrap.cs:16` |
| `CardAggregateQueryJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardAggregateQueryJob.cs:8` |
| `CardBulkDeleteJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardBulkDeleteJob.cs:9` |
| `CardBulkDeleteJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardBulkDeleteJobHandler.cs:15` |
| `CardBulkRegisterJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardBulkRegisterJob.cs:10` |
| `CardBulkRegisterJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardBulkRegisterJobHandler.cs:22` |
| `CardBulkUpdateJob` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardBulkUpdateJob.cs:10` |
| `CardBulkUpdateJobHandler` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Job/CardBulkUpdateJobHandler.cs:21` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Access.cs:16` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Artifact.cs:12` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Entity.cs:14` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.Query.cs:14` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v1/CardController.cs:16` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.Entity.cs:11` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.Query.cs:13` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v2/CardController.cs:14` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.Entity.cs:12` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/external/v3/CardController.cs:14` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Access.cs:12` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Artifact.cs:14` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Entity.cs:20` |
| `CardController` | class | 0 | `catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers/internal/CardController.Patch.cs:14` |

_73 more; use `cdp query module catalog-service/RMS.UnifiedStore.Service.Catalog`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog/(files+4)` | 23 | 1,843 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog/Controllers` | 33 | 5,030 | structural only |
| `root/catalog-service/RMS.UnifiedStore.Service.Catalog/Job` | 59 | 4,260 | structural only |
