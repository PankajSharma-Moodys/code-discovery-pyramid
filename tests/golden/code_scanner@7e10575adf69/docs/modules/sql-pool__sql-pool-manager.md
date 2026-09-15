# `sql-pool/sql-pool-manager`

74 tracked files, 8,554 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/sql-pool/sql-pool-manager/(files+5)`, `root/sql-pool/sql-pool-manager/src/main/(healthcheck+3)`, `root/sql-pool/sql-pool-manager/src/test`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `sql-pool/sql-pool-common` (158 refs), `sql-pool/sql-pool-provision` (33 refs), `sql-pool/sql-pool-service` (57 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ServerStateService` | class | 9 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/service/ServerStateService.java:28` |
| `AutoScaleDelegate` | interface | 3 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/AutoScaleDelegate.java:3` |
| `ApiConstants` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/ApiConstants.java:3` |
| `StatusCheckingAdaptor` | interface | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/adaptor/StatusCheckingAdaptor.java:10` |
| `StatusCheckingAdaptorFactory` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/adaptor/StatusCheckingAdaptorFactory.java:10` |
| `MetricsCalculatorDelegate` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/MetricsCalculatorDelegate.java:16` |
| `ProcessServerHintsDelegate` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/ProcessServerHintsDelegate.java:20` |
| `RevertServersMaintenanceDelegate` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:26` |
| `ServersMaintenanceDelegate` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/ServersMaintenanceDelegate.java:24` |
| `TrackMaxReservationCountDelegate` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/TrackMaxReservationCountDelegate.java:22` |
| `TestHelper` | class | 2 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/helper/TestHelper.java:7` |
| `AutoScaleService` | class | 2 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/service/AutoScaleService.java:21` |
| `QuartzJobsElapsedTimeCheck` | class | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/healthcheck/QuartzJobsElapsedTimeCheck.java:18` |
| `DiskMetrics` | class | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/helper/DiskMetrics.java:3` |
| `DiskMetricsCalculator` | class | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/helper/DiskMetricsCalculator.java:7` |
| `TrackServersUsageJob` | class | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:22` |
| `DecommissionReasons` | enum | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/decommissionreasons/DecommissionReasons.java:3` |
| `DecommissionServerDefinition` | class | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/decommissionreasons/DecommissionServerDefinition.java:3` |
| `DecommissionServerReason` | class | 1 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/decommissionreasons/DecommissionServerReason.java:3` |
| `QuartzRamConfiguration` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/QuartzRamConfiguration.java:8` |
| `SpringContext` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/SpringContext.java:9` |
| `SqlPoolQuartzConfiguration` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/SqlPoolQuartzConfiguration.java:11` |
| `SqlPoolQuartzJobsApplication` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/SqlPoolQuartzJobsApplication.java:29` |
| `SqlPoolSpringConfiguration` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/SqlPoolSpringConfiguration.java:30` |
| `CompositeConnectionCheckingAdaptor` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/adaptor/CompositeConnectionCheckingAdaptor.java:14` |
| `CompositeConnectionCheckingAdaptorTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/adaptor/CompositeConnectionCheckingAdaptorTest.java:12` |
| `SqlConnectionCheckingAdaptor` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/adaptor/SqlConnectionCheckingAdaptor.java:18` |
| `SqlConnectionCheckingAdaptorTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/adaptor/SqlConnectionCheckingAdaptorTest.java:21` |
| `SshCheckingAdaptor` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/adaptor/SshCheckingAdaptor.java:8` |
| `StatusCheckingAdaptorFactoryTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/adaptor/StatusCheckingAdaptorFactoryTest.java:16` |
| `MetricsCalculatorDelegateTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/MetricsCalculatorDelegateTest.java:17` |
| `ProcessServerHintsDelegateTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/ProcessServerHintsDelegateTest.java:19` |
| `RevertServersMaintenanceDelegateTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/RevertServersMaintenanceDelegateTest.java:29` |
| `ServersMaintenanceBaseDelegate` | interface | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/ServersMaintenanceBaseDelegate.java:14` |
| `ServersMaintenanceBaseDelegateTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/ServersMaintenanceBaseDelegateTest.java:15` |
| `DummyServerMaintenanceBaseDelegate` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/ServersMaintenanceBaseDelegateTest.java:190` |
| `ServersMaintenanceDelegateTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/ServersMaintenanceDelegateTest.java:26` |
| `TrackMaxReservationCountDelegateTest` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/TrackMaxReservationCountDelegateTest.java:20` |
| `AutoScaleDelegateV2` | class | 0 | `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/impl/AutoScaleDelegateV2.java:17` |
| `AutoScaleDelegateV2Test` | class | 0 | `sql-pool/sql-pool-manager/src/test/java/RMS/unifiedstore/sqlpool/manager/delegate/impl/AutoScaleDelegateV2Test.java:17` |

_28 more; use `cdp query module sql-pool/sql-pool-manager`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/sql-pool/sql-pool-manager/(files+5)` | 40 | 3,791 | structural only |
| `root/sql-pool/sql-pool-manager/src/main/(healthcheck+3)` | 8 | 280 | structural only |
| `root/sql-pool/sql-pool-manager/src/test` | 26 | 4,483 | structural only |
