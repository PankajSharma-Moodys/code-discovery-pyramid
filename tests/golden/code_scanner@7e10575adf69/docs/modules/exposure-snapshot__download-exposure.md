# `exposure-snapshot/download-exposure`

19 tracked files, 3,510 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/download-exposure`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (1 refs), `client-java/uds-client` (1 refs), `exposure-snapshot/snapshot-common` (36 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-core` (2 refs), `exposure-snapshot/snapshot-sdk` (14 refs)

**Imported by:** `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` (6 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` (2 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `VariationInput` | class | 5 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/task/LiveVariationTask.scala:325` |
| `LiveVariationTask` | class | 2 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/task/LiveVariationTask.scala:54` |
| `ZipUtility` | class | 2 | `exposure-snapshot/download-exposure/src/main/java/com/rms/unifiedstore/utility/ZipUtility.java:14` |
| `DatabaseServer` | class | 2 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/utils/VariationUtils.scala:750` |
| `AccountSnapshotService` | class | 1 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/service/AccountSnapshotService.scala:27` |
| `PortfolioSnapshotService` | class | 1 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/service/PortfolioSnapshotService.scala:27` |
| `SecureLinkService` | class | 1 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/service/SecureLinkService.scala:8` |
| `AccountSnapshotServiceIT` | class | 0 | `exposure-snapshot/download-exposure/src/test/java/com/rms/unifiedstore/AccountSnapshotServiceIT.scala:58` |
| `LiveVariationTaskIT` | class | 0 | `exposure-snapshot/download-exposure/src/test/java/com/rms/unifiedstore/LiveVariationTaskIT.scala:40` |
| `PortfolioSnapshotServiceIT` | class | 0 | `exposure-snapshot/download-exposure/src/test/java/com/rms/unifiedstore/PortfolioSnapshotServiceIT.scala:33` |
| `SecureLinkIT` | class | 0 | `exposure-snapshot/download-exposure/src/test/java/com/rms/unifiedstore/SecureLinkIT.scala:15` |
| `VariationApplicationIT` | class | 0 | `exposure-snapshot/download-exposure/src/test/java/com/rms/unifiedstore/VariationApplicationIT.scala:5` |
| `SecureLinkInput` | class | 0 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/service/SecureLinkService.scala:36` |
| `SnapshotOutput` | class | 0 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/task/LiveVariationTask.scala:354` |
| `VariationOutput` | class | 0 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/task/LiveVariationTask.scala:352` |
| `EdmJdbcPartition` | class | 0 | `exposure-snapshot/download-exposure/src/main/scala/com/rms/unifiedstore/utils/VariationUtils.scala:760` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/download-exposure` | 19 | 3,510 | structural only |
