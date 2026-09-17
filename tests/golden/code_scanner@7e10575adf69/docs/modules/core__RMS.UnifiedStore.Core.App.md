# `core/RMS.UnifiedStore.Core.App`

23 tracked files, 924 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/core/RMS.UnifiedStore.Core.App`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `core/RMS.UnifiedStore.Core` (21 refs)

**Imported by:** `catalog-service/RMS.UnifiedStore.Service.Catalog` (12 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (15 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (1 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Tests` (1 refs), `core/RMS.UnifiedStore.Core.App.Tests` (3 refs), `service-api/RMS.UnifiedStore.Service.Api` (55 refs), `service-api/RMS.UnifiedStore.Service.Api.Tests` (15 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `BadRequestException` | class | 3 | `core/RMS.UnifiedStore.Core.App/Exceptions/BadRequestException.cs:7` |
| `AbstractJobHandler` | class | 0 | `core/RMS.UnifiedStore.Core.App/Job/AbstractJobHandler.cs:8` |
| `Constants` | class | 0 | `core/RMS.UnifiedStore.Core.App/Constants.cs:5` |
| `BackgroundJob` | class | 0 | `core/RMS.UnifiedStore.Core.App/Constants.cs:19` |
| `HealthCheck` | class | 0 | `core/RMS.UnifiedStore.Core.App/Constants.cs:7` |
| `Middleware` | class | 0 | `core/RMS.UnifiedStore.Core.App/Constants.cs:14` |
| `SystemDbsNames` | class | 0 | `core/RMS.UnifiedStore.Core.App/Constants.cs:25` |
| `DebugActionFilter` | class | 0 | `core/RMS.UnifiedStore.Core.App/ActionFilter/DebugActionFilter.cs:9` |
| `DebugMessageHandler` | class | 0 | `core/RMS.UnifiedStore.Core.App/Http/DebugMessageHandler.cs:8` |
| `ExceptionHandlerMiddleware` | class | 0 | `core/RMS.UnifiedStore.Core.App/Middleware/ExceptionHandlerMiddleware.cs:18` |
| `FeatureFlags` | class | 0 | `core/RMS.UnifiedStore.Core.App/App/FeatureFlags.cs:8` |
| `ForbiddenException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/ForbiddenException.cs:7` |
| `InternalServerException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/InternalServerException.cs:6` |
| `NotFoundException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/NotFoundException.cs:7` |
| `ResourceGoneException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/ResourceGoneException.cs:7` |
| `EntityOperationFilterMiddleware` | class | 0 | `core/RMS.UnifiedStore.Core.App/Middleware/EntityOperationFilterMiddleware.cs:8` |
| `EntitySchemaFilterMiddleware` | class | 0 | `core/RMS.UnifiedStore.Core.App/Middleware/EntitySchemaFilterMiddleware.cs:8` |
| `RefitRunner` | class | 0 | `core/RMS.UnifiedStore.Core.App/Http/RefitRunner.cs:10` |
| `ResourceConflictException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/ResourceConflictException.cs:7` |
| `ServiceConfigurationExtensions` | class | 0 | `core/RMS.UnifiedStore.Core.App/ServiceConfigurationExtensions.cs:19` |
| `SingleTaskJobHandler` | class | 0 | `core/RMS.UnifiedStore.Core.App/Job/SingleTaskJobHandler.cs:8` |
| `SingleTaskJobHandler` | class | 0 | `core/RMS.UnifiedStore.Core.App/Job/SingleTaskJobHandler.cs:24` |
| `TooManyRequestsException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/TooManyRequestsException.cs:7` |
| `UnauthorizedException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/UnauthorizedException.cs:7` |
| `WebApiException` | class | 0 | `core/RMS.UnifiedStore.Core.App/Exceptions/WebApiException.cs:7` |
| `WebApiJobHandler` | class | 0 | `core/RMS.UnifiedStore.Core.App/Job/WebApiJobHandler.cs:9` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/core/RMS.UnifiedStore.Core.App` | 23 | 924 | structural only |
