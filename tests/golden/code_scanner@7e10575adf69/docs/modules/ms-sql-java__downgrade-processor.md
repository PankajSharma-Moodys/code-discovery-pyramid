# `ms-sql-java/downgrade-processor`

26 tracked files, 57,123 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/ms-sql-java/downgrade-processor/(files+3)`, `root/ms-sql-java/downgrade-processor/src/main/resources/rollback-scripts`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `SQLReservation` | class | 2 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/SQLReservation.java:3` |
| `ServerVersion` | enum | 2 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/ServerVersion.java:3` |
| `DowngradeResponse` | class | 1 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/DowngradeResponse.java:3` |
| `LocationPair` | record | 1 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/LocationPair.java:3` |
| `LogicalNamesPair` | record | 1 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/LogicalNamesPair.java:3` |
| `Progress` | class | 1 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/Progress.java:3` |
| `WorkflowResult` | class | 1 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/WorkflowResult.java:3` |
| `DatabaseConnectionHelper` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/DatabaseConnectionHelper.java:7` |
| `DowngradeProcessor` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/DowngradeProcessor.java:21` |
| `DowngradeProcessorTest` | class | 0 | `ms-sql-java/downgrade-processor/src/test/java/com/rms/unifiedstore/downgrade/DowngradeProcessorTest.java:7` |
| `EdmRollbackExecutor` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/EdmRollbackExecutor.java:23` |
| `Utils` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/Utils.java:36` |
| `ResultCallback` | interface | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/Utils.java:203` |
| `SQLPool` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/SQLPool.java:3` |
| `SQLPoolResponse` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/SQLPoolResponse.java:6` |
| `SQLServerDetails` | class | 0 | `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/models/SQLServerDetails.java:3` |
| `ProcessException` | class | 0 | `ms-sql-java/downgrade-processor/scripts/winrm_script.py:8` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/ms-sql-java/downgrade-processor/(files+3)` | 19 | 2,592 | structural only |
| `root/ms-sql-java/downgrade-processor/src/main/resources/rollback-scripts` | 7 | 54,531 | structural only |
