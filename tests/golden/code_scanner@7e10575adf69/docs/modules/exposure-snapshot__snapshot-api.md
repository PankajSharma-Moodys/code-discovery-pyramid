# `exposure-snapshot/snapshot-api`

124 tracked files, 17,382 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-api/(files+8)`, `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/(files+5)`, `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp`, `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/(files)`, `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources`, `root/exposure-snapshot/snapshot-api/src/test`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (2 refs), `client-java/uds-client` (33 refs), `exposure-snapshot/idempotency-filter` (3 refs), `exposure-snapshot/ods-domain-data` (12 refs), `exposure-snapshot/snapshot-common` (414 refs), `exposure-snapshot/snapshot-filter-query-service` (5 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (6 refs), `exposure-snapshot/snapshot-sdk` (25 refs), `exposure-snapshot/snapshot-workflow-service` (30 refs), `exposure-snapshot/swagger-resource` (1 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ExposureVariationsImpl` | class | 11 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/ExposureVariationsImpl.java:39` |
| `InternalExposureVariation` | class | 10 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/internal/InternalExposureVariation.java:10` |
| `VariationVersion` | enum | 9 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/enums/VariationVersion.java:3` |
| `SnapshotApiHelper` | class | 8 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotApiHelper.java:35` |
| `TokenGenerator` | class | 8 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/TokenGenerator.java:16` |
| `JobUtils` | class | 7 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/util/JobUtils.java:21` |
| `SnapshotApiValidator` | class | 5 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotApiValidator.java:39` |
| `PortfolioVariationRequest` | class | 5 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/PortfolioVariationRequest.java:7` |
| `SnapshotDbHelper` | class | 4 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotDbHelper.java:12` |
| `AccountVariationRequest` | class | 4 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/AccountVariationRequest.java:7` |
| `EntitySearchResult` | record | 4 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/EntitySearchResult.java:5` |
| `EntitlementService` | class | 4 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/service/entitlement/EntitlementService.java:13` |
| `WFSUtils` | class | 4 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/util/WFSUtils.java:18` |
| `VariationsImpl` | class | 3 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/VariationsImpl.java:32` |
| `EntityVariationResponse` | class | 3 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/EntityVariationResponse.java:3` |
| `ExposureVariations` | class | 3 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/ExposureVariations.java:10` |
| `RefreshAgExecutorServiceHelper` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/RefreshAgExecutorServiceHelper.java:13` |
| `RegexPatternHelper` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/RegexPatternHelper.java:11` |
| `FilterParser` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/query/FilterParser.java:10` |
| `SortParser` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/query/SortParser.java:11` |
| `AccountVariationsImpl` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v1/AccountVariationsImpl.java:44` |
| `ExposureVariationsImplV1` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v1/ExposureVariationsImplV1.java:41` |
| `PortfolioVariationsImpl` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v1/PortfolioVariationsImpl.java:42` |
| `CreateExposureVariationV2JobImpl` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v2/CreateExposureVariationV2JobImpl.java:45` |
| `ExposureVariationsImplV2` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v2/ExposureVariationsImplV2.java:44` |
| `AccountTreatyMap` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/AccountTreatyMap.java:5` |
| `CurrencyInfo` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/CurrencyInfo.java:7` |
| `ExposureVariationStats` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/ExposureVariationStats.java:6` |
| `SnapshotVariationDetailsJson` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/SnapshotVariationDetailsJson.java:3` |
| `EntityVariationService` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/service/EntityVariationService.java:67` |
| `ResourceGroupService` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/service/ResourceGroupService.java:19` |
| `TenantQueueService` | class | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/service/TenantQueueService.java:17` |
| `Entitlements` | enum | 2 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/service/entitlement/Entitlements.java:9` |
| `Actions` | class | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/authorization/Actions.java:8` |
| `LoggingFilter` | class | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/filters/LoggingFilter.java:13` |
| `ResourceGroupRequestFilter` | class | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/filters/ResourceGroupRequestFilter.java:21` |
| `ResourceGroupHelper` | class | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/ResourceGroupHelper.java:7` |
| `IExposureVariationsImpl` | interface | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v1/IExposureVariationsImpl.java:7` |
| `ExceptionMapperBinder` | class | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/mapper/ExceptionMapperBinder.java:7` |
| `AccountVariationMap` | class | 1 | `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/AccountVariationMap.java:3` |

_70 more; use `cdp query module exposure-snapshot/snapshot-api`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-api/(files+8)` | 26 | 1,623 | structural only |
| `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/(files+5)` | 40 | 4,643 | structural only |
| `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp` | 14 | 3,419 | structural only |
| `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/model/(files)` | 25 | 1,314 | structural only |
| `root/exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources` | 6 | 3,264 | structural only |
| `root/exposure-snapshot/snapshot-api/src/test` | 13 | 3,119 | structural only |
