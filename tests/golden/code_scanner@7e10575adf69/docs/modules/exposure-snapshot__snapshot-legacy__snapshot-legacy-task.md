# `exposure-snapshot/snapshot-legacy/snapshot-legacy-task`

23 tracked files, 4,670 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-legacy/snapshot-legacy-task`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/uds-client` (1 refs), `exposure-snapshot/download-exposure` (2 refs), `exposure-snapshot/snapshot-common` (56 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (2 refs), `exposure-snapshot/snapshot-sdk` (26 refs), `exposure-snapshot/snapshot-smoketest` (1 refs), `exposure-snapshot/snapshot-workflow-service` (1 refs)

**Imported by:** `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` (6 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `DatabaseServer` | class | 1 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/SnapshotUtils.scala:766` |
| `EdmJdbcPartition` | class | 1 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/SnapshotUtils.scala:776` |
| `SnapshotGenerationService` | class | 1 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/SnapshotGenerationService.scala:45` |
| `AccountSnapshotInput` | class | 1 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala:339` |
| `AccountSnapshotTask` | class | 1 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala:40` |
| `PortfolioSnapshotTask` | class | 1 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala:71` |
| `AccountSnapshotGenerationService` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/AccountSnapshotGenerationService.scala:47` |
| `EdmLease` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/EdmLease.scala:3` |
| `EdmLeaseService` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/EdmLeaseService.scala:24` |
| `EdmLeaseTest` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/test/scala/com/rms/unifiedstore/service/EdmLeaseServiceTest.scala:21` |
| `LeaseObject` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/LeaseObject.scala:3` |
| `PartitionMatrixService` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/PartitionMatrixService.scala:16` |
| `RiskByPerilWorkflowTaskService` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/service/RiskByPerilWorkflowTaskService.scala:19` |
| `RiskByPerilWorkflowTaskServiceTest` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/test/scala/com/rms/unifiedstore/service/RiskByPerilWorkflowTaskServiceTest.scala:17` |
| `AccountSnapshotOutput` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/AccountSnapshotTask.scala:391` |
| `AccountSnapshotTaskTest` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/test/scala/com/rms/unifiedstore/task/AccountSnapshotTaskTest.scala:13` |
| `PortTreatyMapTest` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/test/scala/com/rms/unifiedstore/task/PortTreatyMapTest.scala:14` |
| `PortfolioSnapshotInputDelegate` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala:68` |
| `PortfolioSnapshotOutput` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala:772` |
| `PortfolioSnapshotTaskTest` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/test/scala/com/rms/unifiedstore/task/PortfolioSnapshotTaskTest.scala:23` |
| `PortfolioSnapshotTaskUnitTest` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/test/scala/com/rms/unifiedstore/task/PortfolioSnapshotTaskUnitTest.scala:11` |
| `SnapshotJobOutput` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala:780` |
| `VariationInfo` | class | 0 | `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/src/main/scala/com/rms/unifiedstore/task/PortfolioSnapshotTask.scala:774` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-legacy/snapshot-legacy-task` | 23 | 4,670 | structural only |
