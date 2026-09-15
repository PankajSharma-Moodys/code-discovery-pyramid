# `sql-pool/sql-pool-api`

49 tracked files, 4,038 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/sql-pool/sql-pool-api/(files+2)`, `root/sql-pool/sql-pool-api/src/main/java`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `sql-pool/sql-pool-common` (52 refs), `sql-pool/sql-pool-service` (5 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `ApiConstants` | class | 4 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/constants/ApiConstants.java:3` |
| `Reservation` | class | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/Reservation.java:11` |
| `ReservationOutput` | class | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ReservationOutput.java:13` |
| `ReservationUpdate` | class | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ReservationUpdate.java:9` |
| `ServerResourceUsageLog` | class | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ServerResourceUsageLog.java:11` |
| `ServerInstanceType` | enum | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/enumerates/ServerInstanceType.java:3` |
| `ServerType` | enum | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/enumerates/ServerType.java:3` |
| `ServerMapper` | interface | 2 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/mappers/ServerMapper.java:20` |
| `SPMExceptionMapper` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/errorhandling/SPMExceptionMapper.java:11` |
| `UnbrandedErrorHandler` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/errorhandling/UnbrandedErrorHandler.java:11` |
| `RequestIdLoggingFilter` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/filters/RequestIdLoggingFilter.java:19` |
| `SwaggerToOpenApiFilter` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/filters/SwaggerToOpenApiFilter.java:13` |
| `PoolConfigDetailedOutput` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/PoolConfigDetailedOutput.java:7` |
| `PoolConfigOutput` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/PoolConfigOutput.java:11` |
| `PoolConfigUpdate` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/PoolConfigUpdate.java:8` |
| `ReservationList` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ReservationList.java:6` |
| `Server` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/Server.java:14` |
| `ServerOutput` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ServerOutput.java:13` |
| `ServerStatusLogOutput` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ServerStatusLogOutput.java:11` |
| `ServerUpdate` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ServerUpdate.java:13` |
| `SqlPoolHealthCheckResponse` | class | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/SqlPoolHealthCheckResponse.java:9` |
| `PoolConfigMapper` | interface | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/mappers/PoolConfigMapper.java:14` |
| `ReservationMapper` | interface | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/mappers/ReservationMapper.java:21` |
| `ServerResourceUsageLogMapper` | interface | 1 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/mappers/ServerResourceUsageLogMapper.java:12` |
| `GetS2STokenTest` | class | 0 | `sql-pool/sql-pool-api/src/test/java/RMS/unifiedstore/sqlpool/api/GetS2STokenTest.java:8` |
| `SqlPoolApplication` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/SqlPoolApplication.java:29` |
| `SqlPoolDropwizardConfiguration` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/SqlPoolDropwizardConfiguration.java:9` |
| `SqlPoolSpringConfiguration` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/SqlPoolSpringConfiguration.java:21` |
| `RequestIdLoggingFilterTest` | class | 0 | `sql-pool/sql-pool-api/src/test/java/RMS/unifiedstore/sqlpool/api/filters/RequestIdLoggingFilterTest.java:14` |
| `Batch` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/Batch.java:10` |
| `DriveUsage` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/DriveUsage.java:7` |
| `PoolConfigList` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/PoolConfigList.java:6` |
| `ServerList` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ServerList.java:7` |
| `ServerStatusLogList` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/dtos/ServerStatusLogList.java:7` |
| `HostAndPortMapper` | interface | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/model/mappers/HostAndPortMapper.java:7` |
| `ReservationMapperTest` | class | 0 | `sql-pool/sql-pool-api/src/test/java/RMS/unifiedstore/sqlpool/api/model/mappers/ReservationMapperTest.java:12` |
| `ServerMapperTest` | class | 0 | `sql-pool/sql-pool-api/src/test/java/RMS/unifiedstore/sqlpool/api/model/mappers/ServerMapperTest.java:14` |
| `ServerResourceUsageLogMapperTest` | class | 0 | `sql-pool/sql-pool-api/src/test/java/RMS/unifiedstore/sqlpool/api/model/mappers/ServerResourceUsageLogMapperTest.java:10` |
| `PoolConfigResource` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/PoolConfigResource.java:53` |
| `ReservationResource` | class | 0 | `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/resources/ReservationResource.java:56` |

_2 more; use `cdp query module sql-pool/sql-pool-api`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/sql-pool/sql-pool-api/(files+2)` | 11 | 648 | structural only |
| `root/sql-pool/sql-pool-api/src/main/java` | 38 | 3,390 | structural only |
