# `exposure-snapshot/snapshot-workflow-service`

32 tracked files, 2,621 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-workflow-service`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `exposure-snapshot/snapshot-common` (23 refs), `exposure-snapshot/snapshot-filter-query-service` (1 refs)

**Imported by:** `exposure-snapshot/snapshot-api` (30 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `QuotaReservation` | class | 6 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/QuotaReservation.java:5` |
| `Job` | class | 6 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/search/Job.java:7` |
| `JobSummary` | class | 5 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/JobSummary.java:8` |
| `WorkflowExecution` | class | 5 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/WorkflowExecution.java:6` |
| `JobSearchResult` | class | 5 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/search/JobSearchResult.java:6` |
| `JobType` | enum | 5 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/search/JobType.java:5` |
| `Priority` | enum | 4 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/Priority.java:3` |
| `WorkflowSearchService` | interface | 3 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/WorkflowSearchService.java:8` |
| `WorkflowUpdateService` | interface | 3 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/WorkflowUpdateService.java:7` |
| `QuotaConstants` | class | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/constants/QuotaConstants.java:8` |
| `JobDetail` | class | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/JobDetail.java:5` |
| `JobPatchRequest` | class | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/JobPatchRequest.java:5` |
| `Status` | enum | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/Status.java:3` |
| `WorkflowExecutionList` | class | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/WorkflowExecutionList.java:5` |
| `WorkflowServiceTask` | class | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/WorkflowServiceTask.java:8` |
| `WorkflowStatus` | enum | 2 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/WorkflowStatus.java:3` |
| `V2WorkflowConnector` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/V2WorkflowConnector.java:30` |
| `WorkflowSearchServiceImpl` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/WorkflowSearchServiceImpl.java:45` |
| `WorkflowService` | interface | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/WorkflowService.java:10` |
| `WorkflowUpdateServiceImpl` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/WorkflowUpdateServiceImpl.java:17` |
| `V2WorkflowHelper` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/helper/V2WorkflowHelper.java:21` |
| `WorkflowMapper` | interface | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/mapper/WorkflowMapper.java:7` |
| `ApiTaskOutput` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/ApiTaskOutput.java:6` |
| `Detail` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/Detail.java:6` |
| `JobResult` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/JobResult.java:5` |
| `JobStatus` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/JobStatus.java:3` |
| `JobMessage` | class | 1 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/search/JobMessage.java:3` |
| `WorkflowColumnConstants` | class | 0 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/constants/WorkflowColumnConstants.java:3` |
| `DefaultWorkflowMapper` | class | 0 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/mapper/DefaultWorkflowMapper.java:31` |
| `TaskErrorMessage` | class | 0 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/ApiTaskOutput.java:48` |
| `JobToWorkflowStatus` | enum | 0 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/JobToWorkflowStatus.java:3` |
| `SortField` | enum | 0 | `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/model/SortField.java:3` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-workflow-service` | 32 | 2,621 | structural only |
