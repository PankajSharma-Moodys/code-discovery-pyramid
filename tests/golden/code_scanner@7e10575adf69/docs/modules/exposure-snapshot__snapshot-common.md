# `exposure-snapshot/snapshot-common`

220 tracked files, 16,249 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-common/(files+5)`, `root/exposure-snapshot/snapshot-common/src/main/(files+5)`, `root/exposure-snapshot/snapshot-common/src/main/(files+9)`, `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/(clients+3)`, `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/(files)`, `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/(files)`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/idempotency-filter` (2 refs), `exposure-snapshot/ods-domain-data` (13 refs), `exposure-snapshot/snapshot-api` (414 refs), `exposure-snapshot/snapshot-developer-utils` (4 refs), `exposure-snapshot/snapshot-filter-query-service` (53 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (3 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition` (1 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform` (1 refs), `exposure-snapshot/snapshot-sdk` (20 refs), `exposure-snapshot/snapshot-task-create` (13 refs), `exposure-snapshot/snapshot-task-delete` (8 refs), `exposure-snapshot/snapshot-workflow-service` (23 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ExposureSnapshotException` | class | 37 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ExposureSnapshotException.java:3` |
| `CoreConstants` | class | 28 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/CoreConstants.java:6` |
| `SnapshotConfiguration` | class | 25 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/SnapshotConfiguration.java:13` |
| `ErrorCode` | interface | 23 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ErrorCode.java:5` |
| `ThreadContext` | class | 22 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/ThreadContext.java:6` |
| `DataType` | enum | 20 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/DataType.java:10` |
| `Utils` | class | 20 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/workflow/helper/Utils.java:24` |
| `ApiConstants` | class | 17 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:6` |
| `SnapshotTaskKeys` | class | 15 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/payload/SnapshotTaskKeys.java:4` |
| `Value` | interface | 14 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/Value.java:7` |
| `VariationsErrorCode` | enum | 13 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/VariationsErrorCode.java:7` |
| `ErrorMessage` | class | 12 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ErrorMessage.java:5` |
| `ContextConstants` | class | 12 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ContextConstants.java:3` |
| `ExposureType` | enum | 11 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/data/ExposureType.java:5` |
| `SqlSerializable` | interface | 11 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/SqlSerializable.java:8` |
| `FailsafeUtil` | class | 10 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/FailsafeUtil.java:16` |
| `VariationsErrorCode` | enum | 9 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/error/VariationsErrorCode.java:6` |
| `FeatureFlagService` | class | 9 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/featureflag/FeatureFlagService.java:8` |
| `ErrorMessageLoader` | class | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ErrorMessageLoader.java:5` |
| `WorkflowTypes` | enum | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/WorkflowTypes.java:3` |
| `ClientErrorCode` | enum | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/ClientErrorCode.java:7` |
| `Identifier` | class | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/Identifier.java:9` |
| `RelationalOperator` | enum | 7 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/query/RelationalOperator.java:5` |
| `ResourceUriUtils` | class | 7 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/ResourceUriUtils.java:13` |
| `SortBy` | class | 6 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/SortBy.java:7` |
| `VariationInput` | class | 6 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/variations/VariationInput.java:29` |
| `SortOrder` | enum | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/query/SortOrder.java:3` |
| `ExposureTable` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/schema/ExposureTable.java:6` |
| `CardInfo` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/variations/CardInfo.java:3` |
| `ResourceUriComponent` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/ResourceUriComponent.java:5` |
| `SnapshotStatus` | enum | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/workflow/helper/SnapshotStatus.java:3` |
| `EntityType` | class | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/EntityType.java:4` |
| `BooleanOperator` | enum | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/query/BooleanOperator.java:3` |
| `TaskMDCInitializer` | class | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/helper/TaskMDCInitializer.java:17` |
| `Condition` | interface | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/Condition.java:17` |
| `Expression` | interface | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/Expression.java:26` |
| `PortfolioSettingsInput` | class | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/variations/PortfolioSettingsInput.java:13` |
| `ContextAwareCallable` | class | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/ContextAwareCallable.java:10` |
| `DateFormatter` | class | 3 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/DateFormatter.java:15` |
| `AnalyticsGatewayClient` | class | 3 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/clients/AnalyticsGatewayClient.java:25` |

_179 more; use `cdp query module exposure-snapshot/snapshot-common`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-common/(files+5)` | 40 | 2,838 | structural only |
| `root/exposure-snapshot/snapshot-common/src/main/(files+5)` | 40 | 1,772 | structural only |
| `root/exposure-snapshot/snapshot-common/src/main/(files+9)` | 28 | 1,028 | structural only |
| `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/(clients+3)` | 40 | 3,832 | structural only |
| `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/(files)` | 31 | 2,893 | structural only |
| `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/(files)` | 41 | 3,886 | structural only |
