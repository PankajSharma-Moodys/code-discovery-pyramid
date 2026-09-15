# `exposure-snapshot/snapshot-task-create`

22 tracked files, 1,430 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-task-create`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/uds-client` (2 refs), `exposure-snapshot/snapshot-common` (13 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `LambdaSnapshotEdmBundleRequest` | class | 2 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/lambda/model/LambdaSnapshotEdmBundleRequest.java:6` |
| `LambdaSnapshotEdmBundleResponse` | class | 2 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/lambda/model/LambdaSnapshotEdmBundleResponse.java:9` |
| `JobExecutionStatusResponse` | class | 2 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/model/JobExecutionStatusResponse.java:4` |
| `ModelPlatformServiceConstants` | class | 2 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/model/ModelPlatformServiceConstants.java:3` |
| `JobProgressClient` | interface | 2 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/workflow_service/JobProgressClient.java:9` |
| `EngineException` | class | 1 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/exception/EngineException.java:6` |
| `EdmBundleConstants` | class | 1 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/lambda/constants/EdmBundleConstants.java:3` |
| `LambdaSnapshotEdmBundleJobRequest` | class | 1 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/lambda/model/LambdaSnapshotEdmBundleJobRequest.java:3` |
| `ModelPlatformJobFailedException` | class | 1 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/exception/ModelPlatformJobFailedException.java:4` |
| `ModelPlatformJobResponse` | class | 1 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/model/ModelPlatformJobResponse.java:3` |
| `ModelPlatformServiceHelper` | class | 1 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/utils/ModelPlatformServiceHelper.java:40` |
| `EdmBundleManager` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/EdmBundleManager.java:33` |
| `ModelPlatformJobSubmitRejectedException` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/exception/ModelPlatformJobSubmitRejectedException.java:4` |
| `UnableToDeleteModelPlatformJobException` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/exception/UnableToDeleteModelPlatformJobException.java:4` |
| `UnableToGetModelPlatformJobStatusException` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/exception/UnableToGetModelPlatformJobStatusException.java:4` |
| `UnableToSubmitModelPlatformJobException` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/exception/UnableToSubmitModelPlatformJobException.java:4` |
| `JobServiceResponse` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/model_platform/utils/ModelPlatformServiceHelper.java:430` |
| `ManagedEventBus` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/workflow_service/ManagedEventBus.java:22` |
| `PoisonPill` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/workflow_service/ManagedEventBus.java:70` |
| `ProgressInput` | class | 0 | `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/workflow_service/ProgressInput.java:5` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-task-create` | 22 | 1,430 | structural only |
