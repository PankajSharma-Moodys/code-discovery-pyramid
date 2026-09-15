# `sql-pool/sql-pool-service`

23 tracked files, 5,821 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/sql-pool/sql-pool-service`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `sql-pool/sql-pool-common` (79 refs), `sql-pool/sql-pool-dal` (30 refs)

**Imported by:** `sql-pool/sql-pool-api` (5 refs), `sql-pool/sql-pool-manager` (57 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ServerService` | class | 36 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:24` |
| `ReservationService` | class | 18 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:37` |
| `DServerMapper` | interface | 5 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:17` |
| `PoolConfigService` | class | 5 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/PoolConfigService.java:19` |
| `CleanUpFailedToProvisionServerMetric` | class | 4 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/eventbus/events/CleanUpFailedToProvisionServerMetric.java:15` |
| `FailedToProvisionServerMetricEvent` | class | 4 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/eventbus/events/FailedToProvisionServerMetricEvent.java:15` |
| `ServerStatusChangeEvent` | class | 4 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/eventbus/events/ServerStatusChangeEvent.java:17` |
| `DPoolConfigMapper` | interface | 2 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:13` |
| `DReservationMapper` | interface | 2 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMapper.java:13` |
| `ServerSubscriber` | class | 1 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/eventbus/subscribe/ServerSubscriber.java:40` |
| `DDiskThresholdsParser` | class | 1 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/helper/DDiskThresholdsParser.java:14` |
| `ServerSubscriberTest` | class | 0 | `sql-pool/sql-pool-service/src/test/java/RMS/UnifiedStore/sqlpool/service/eventbus/subscribe/ServerSubscriberTest.java:23` |
| `DDiskThresholdsParserTest` | class | 0 | `sql-pool/sql-pool-service/src/test/java/RMS/UnifiedStore/sqlpool/service/helper/DDiskThresholdsParserTest.java:9` |
| `DReservationMetadataMapper` | interface | 0 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMetadataMapper.java:12` |
| `DServerMapperTest` | class | 0 | `sql-pool/sql-pool-service/src/test/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapperTest.java:17` |
| `DiskThresholdsMapper` | interface | 0 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DiskThresholdsMapper.java:7` |
| `DiskUsageResultParser` | interface | 0 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DiskUsageResultParser.java:7` |
| `EncryptionMapper` | interface | 0 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/EncryptionMapper.java:6` |
| `PoolConfigServiceTest` | class | 0 | `sql-pool/sql-pool-service/src/test/java/RMS/UnifiedStore/sqlpool/service/services/PoolConfigServiceTest.java:25` |
| `ReservationServiceTest` | class | 0 | `sql-pool/sql-pool-service/src/test/java/RMS/UnifiedStore/sqlpool/service/services/ReservationServiceTest.java:28` |
| `ServerHelperService` | class | 0 | `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerHelperService.java:26` |
| `ServerServiceTest` | class | 0 | `sql-pool/sql-pool-service/src/test/java/RMS/UnifiedStore/sqlpool/service/services/ServerServiceTest.java:30` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/sql-pool/sql-pool-service` | 23 | 5,821 | structural only |
