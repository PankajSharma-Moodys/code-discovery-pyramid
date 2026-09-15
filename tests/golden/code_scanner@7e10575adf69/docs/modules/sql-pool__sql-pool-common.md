# `sql-pool/sql-pool-common`

90 tracked files, 6,400 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/sql-pool/sql-pool-common/(files+4)`, `root/sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/(exceptions+3)`, `root/sql-pool/sql-pool-common/src/test`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** `sql-pool/sql-pool-api` (52 refs), `sql-pool/sql-pool-dal` (15 refs), `sql-pool/sql-pool-integrationtest` (78 refs), `sql-pool/sql-pool-manager` (158 refs), `sql-pool/sql-pool-provision` (15 refs), `sql-pool/sql-pool-service` (79 refs), `sql-pool/sql-pool-setup` (4 refs), `sql-pool/sql-pool-smoketest` (8 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `DServer` | class | 62 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DServer.java:8` |
| `Constants` | class | 50 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/Constants.java:5` |
| `DServerStatus` | enum | 45 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DServerStatus.java:3` |
| `DServerType` | enum | 37 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DServerType.java:3` |
| `SPMException` | class | 27 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/exceptions/SPMException.java:3` |
| `DReservationStatus` | enum | 20 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DReservationStatus.java:3` |
| `DPoolConfig` | class | 19 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DPoolConfig.java:6` |
| `ServerHelperFactory` | class | 18 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/ServerHelperFactory.java:19` |
| `DServerInstanceType` | enum | 18 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DServerInstanceType.java:3` |
| `ServerHelper` | class | 16 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/ServerHelper.java:18` |
| `LoggerContext` | class | 14 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/LoggerContext.java:8` |
| `ConnectionFactory` | class | 14 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/ConnectionFactory.java:12` |
| `ReduceStrategy` | interface | 14 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/selector/ReduceStrategy.java:5` |
| `EncryptionUtil` | class | 14 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/EncryptionUtil.java:7` |
| `ServerManagementMode` | enum | 13 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/constants/ServerManagementMode.java:3` |
| `DReservation` | class | 13 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DReservation.java:7` |
| `ServerHint` | enum | 10 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/ServerHint.java:3` |
| `GenericMapper` | class | 8 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/mappers/GenericMapper.java:11` |
| `Metrics` | interface | 7 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/metrics/Metrics.java:5` |
| `DDiskUsageResult` | class | 7 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DDiskUsageResult.java:7` |
| `DServerResourceUsageLog` | class | 7 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DServerResourceUsageLog.java:6` |
| `DServerStatusLog` | class | 6 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DServerStatusLog.java:6` |
| `StringUtil` | class | 5 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/StringUtil.java:3` |
| `DDriveUsage` | class | 4 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DDriveUsage.java:3` |
| `DiskIOStats` | class | 4 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DiskIOStats.java:3` |
| `GreenMetadataDbConnection` | class | 4 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/GreenMetadataDbConnection.java:10` |
| `ServerCapacityProvider` | class | 4 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/ServerCapacityProvider.java:7` |
| `ServerUtil` | class | 4 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/ServerUtil.java:10` |
| `SshCommandExecutorFactory` | class | 3 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/ssh/SshCommandExecutorFactory.java:8` |
| `DDiskThresholds` | class | 3 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DDiskThresholds.java:6` |
| `DReservationFetchParams` | class | 3 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DReservationFetchParams.java:5` |
| `LoggerEventsRecorder` | interface | 3 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/util/LoggerEventsRecorder.java:7` |
| `WindowsDiskUsageResultParser` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/disk/WindowsDiskUsageResultParser.java:11` |
| `SshCommandExecutor` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/ssh/SshCommandExecutor.java:16` |
| `MSSQLUserManagedServerHelper` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/usermanaged/MSSQLUserManagedServerHelper.java:8` |
| `PostgresUserManagedServerHelper` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/helper/usermanaged/PostgresUserManagedServerHelper.java:8` |
| `QuartzMetricsImpl` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/metrics/QuartzMetricsImpl.java:7` |
| `DDiskThreshold` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DDiskThreshold.java:3` |
| `DReservationMetadata` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/domain/DReservationMetadata.java:5` |
| `Selector` | class | 2 | `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/selector/Selector.java:7` |

_49 more; use `cdp query module sql-pool/sql-pool-common`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/sql-pool/sql-pool-common/(files+4)` | 40 | 3,595 | structural only |
| `root/sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/(exceptions+3)` | 28 | 894 | structural only |
| `root/sql-pool/sql-pool-common/src/test` | 22 | 1,911 | structural only |
