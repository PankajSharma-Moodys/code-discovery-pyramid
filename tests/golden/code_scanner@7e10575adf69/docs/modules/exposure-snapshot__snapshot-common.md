# `exposure-snapshot/snapshot-common`

220 tracked files, 16,249 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-common/(files+5)`, `root/exposure-snapshot/snapshot-common/src/main/(files+5)`, `root/exposure-snapshot/snapshot-common/src/main/(files+9)`, `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/(clients+3)`, `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/(files)`, `root/exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/(files)`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/download-exposure` (36 refs), `exposure-snapshot/idempotency-filter` (2 refs), `exposure-snapshot/ods-domain-data` (13 refs), `exposure-snapshot/snapshot-api` (408 refs), `exposure-snapshot/snapshot-developer-utils` (4 refs), `exposure-snapshot/snapshot-filter-query-service` (53 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` (8 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (3 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition` (1 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` (56 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform` (1 refs), `exposure-snapshot/snapshot-migration` (11 refs), `exposure-snapshot/snapshot-sdk` (31 refs), `exposure-snapshot/snapshot-task-create` (13 refs), `exposure-snapshot/snapshot-task-delete` (7 refs), `exposure-snapshot/snapshot-workflow-service` (23 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ExposureSnapshotException` | class | 47 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ExposureSnapshotException.java:3` |
| `CoreConstants` | class | 32 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/CoreConstants.java:6` |
| `SnapshotConfiguration` | class | 29 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/SnapshotConfiguration.java:13` |
| `Utils` | class | 29 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/workflow/helper/Utils.java:24` |
| `ErrorCode` | interface | 23 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ErrorCode.java:5` |
| `ThreadContext` | class | 22 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/ThreadContext.java:6` |
| `DataType` | enum | 20 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/DataType.java:10` |
| `SnapshotTaskKeys` | class | 18 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/payload/SnapshotTaskKeys.java:4` |
| `FailsafeUtil` | class | 18 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/FailsafeUtil.java:16` |
| `ApiConstants` | class | 17 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:6` |
| `VariationsErrorCode` | enum | 15 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/VariationsErrorCode.java:7` |
| `Value` | interface | 14 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/Value.java:7` |
| `VariationsErrorCode` | enum | 13 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/error/VariationsErrorCode.java:6` |
| `ErrorMessage` | class | 12 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ErrorMessage.java:5` |
| `ContextConstants` | class | 12 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ContextConstants.java:3` |
| `ExposureType` | enum | 11 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/data/ExposureType.java:5` |
| `SqlSerializable` | interface | 11 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/SqlSerializable.java:8` |
| `PortfolioVariationIdMapping` | class | 10 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/workflow/model/PortfolioVariationIdMapping.java:5` |
| `FeatureFlagService` | class | 9 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/featureflag/FeatureFlagService.java:8` |
| `SnapshotStatus` | enum | 9 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/workflow/helper/SnapshotStatus.java:3` |
| `ErrorMessageLoader` | class | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/ErrorMessageLoader.java:5` |
| `WorkflowTypes` | enum | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/WorkflowTypes.java:3` |
| `ClientErrorCode` | enum | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/ClientErrorCode.java:7` |
| `Identifier` | class | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/Identifier.java:9` |
| `PartitionKeys` | class | 8 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/payload/PartitionKeys.java:3` |
| `RelationalOperator` | enum | 7 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/query/RelationalOperator.java:5` |
| `TaskMDCInitializer` | class | 7 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/helper/TaskMDCInitializer.java:17` |
| `ResourceUriUtils` | class | 7 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/ResourceUriUtils.java:13` |
| `AnalyticsGatewayClient` | class | 6 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/clients/AnalyticsGatewayClient.java:25` |
| `SortBy` | class | 6 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/query/SortBy.java:7` |
| `VariationInput` | class | 6 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/variations/VariationInput.java:29` |
| `PortfolioSnapshotInput` | class | 6 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/tasks/v1/portfoliosnapshot/PortfolioSnapshotInput.java:5` |
| `SortOrder` | enum | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/query/SortOrder.java:3` |
| `ExposureTable` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/schema/ExposureTable.java:6` |
| `CardInfo` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/variations/CardInfo.java:3` |
| `ResourceUriComponent` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/utils/ResourceUriComponent.java:5` |
| `AccountVariationIdMapping` | class | 5 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/workflow/model/AccountVariationIdMapping.java:5` |
| `EntityType` | class | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/EntityType.java:4` |
| `BooleanOperator` | enum | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/enums/query/BooleanOperator.java:3` |
| `ProvisioningStatus` | enum | 4 | `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/model/provision/ProvisioningStatus.java:5` |

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
