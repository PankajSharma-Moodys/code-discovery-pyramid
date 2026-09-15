# Data flow

How data travels through this application — the question the module dependency graph cannot answer. The topology below was walked by deterministic Python over typed channel edges; every hop carries the anchor of the edge it came from, so a hop with no evidence has nowhere to hide.

> **Coverage: 0.0%** — 0 of 4728 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/(.github+3)`, `root/(build+5)`, `root/(files)`, `root/.claude`, `root/.cursor`, `root/automation`, `root/automation/api-automation/(files+10)`, `root/automation/api-automation/src/main/java/com/rms/uds/tests`.

## Edges that no import expresses

Modules that exchange data through shared storage. These are real data edges with zero code-level coupling; a dependency graph cannot see them, and a reader told "a depends on b depends on c" will not expect them.

- **`SqlPoolApplication` and `RegenerateSchemaBaseline` and `SqlPoolQuartzJobsApplication`** (modules `sql-pool/sql-pool-api`, `sql-pool/sql-pool-integrationtest`, `sql-pool/sql-pool-manager`)
  - tables: `pool_config`, `reservation`, `reservation_metadata`, `server`, `server_metadata`, `server_resource_usage_log`, `server_status_log`
  - entities: `EPoolConfig`, `EReservation`, `EReservationMetadata`, `EServer`, `EServerResourceUsageLog`, `EServerStatusLog`
  - `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/SqlPoolApplication.java:33` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/repository/EConfigPoolRepository.java:8` `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/schema/RegenerateSchemaBaseline.java:28` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/repository/EConfigPoolRepository.java:8`
  - _SqlPoolApplication and RegenerateSchemaBaseline and SqlPoolQuartzJobsApplication are separate deployable units whose dependency closures both contain code that touches entity:rms.unifiedstore.sqlpool.dal.entities.EPoolConfig. No import connects the two application classes; the data edge exists only through shared storage. This is reachability over packaged code, not an observed runtime call._

## Representation chains

Where one record exists under several names. Each hop is a mapper; the chain is what a reader has to know before `EServer`, `DServer` and `Server` stop looking like three different things.

- `DPoolConfig` -> `EPoolConfig`
  - reached from `CheckDecommissionServerStatusJob` (schedule)
  - `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `DReservationMetadata` -> `EReservationMetadata`
  - reached from `CheckDecommissionServerStatusJob` (schedule)
  - `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMetadataMapper.java:18`
- `DServer` -> `EServer`
  - reached from `CheckDecommissionServerStatusJob` (schedule)
  - `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `DReservation` -> `EReservation`
  - reached from `CheckExpiredReservationTtlJob` (schedule)
  - `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMapper.java:31`

## Traced paths

From every entry point to every reachable sink. `call` hops are derived from the import table: an import proves a file *can* reach a symbol, not that it does, so any path containing one is marked medium confidence.

### `process:ms-sql-java.downgrade-processor.scripts.winrm_script`

_process_boundary, high confidence, modules: ms-sql-java/downgrade-processor_

```
ms-sql-java.downgrade-processor.scripts.winrm_script
  --persist--> table:the
```

- `winrm_script` --persist--> `table:the` `ms-sql-java/downgrade-processor/scripts/winrm_script.py:417`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `CheckDecommissionServerStatusJob` --call--> `DPoolConfig` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckDecommissionServerStatusJob.java:14`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-common, sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.common.model.mappers.GenericMapper
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DReservationMetadata
  --map--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `CheckDecommissionServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckDecommissionServerStatusJob.java:22`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `GenericMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:9`
- `GenericMapper` --call--> `DReservationMetadata` `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/mappers/GenericMapper.java:7`
- `DReservationMetadata` --map--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMetadataMapper.java:18`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `CheckDecommissionServerStatusJob` --call--> `DServer` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckDecommissionServerStatusJob.java:15`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `CheckDecommissionServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckDecommissionServerStatusJob.java:22`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckDecommissionServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `CheckDecommissionServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckDecommissionServerStatusJob.java:22`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DReservation
  --map--> rms.unifiedstore.sqlpool.dal.entities.EReservation
  --persist--> table:reservation
```

- `CheckExpiredReservationTtlJob` --call--> `DReservation` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckExpiredReservationTtlJob.java:13`
- `DReservation` --map--> `EReservation` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMapper.java:31`
- `EReservation` --persist--> `table:reservation` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservation.java:10`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `CheckExpiredReservationTtlJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckExpiredReservationTtlJob.java:17`
- `ReservationService` --call--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:29`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `CheckExpiredReservationTtlJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckExpiredReservationTtlJob.java:17`
- `ReservationService` --call--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:30`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `CheckExpiredReservationTtlJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckExpiredReservationTtlJob.java:17`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckExpiredReservationTtlJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `CheckExpiredReservationTtlJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckExpiredReservationTtlJob.java:17`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.RevertServersMaintenanceDelegate
  --call--> rms.unifiedstore.sqlpool.manager.service.ServerStateService
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `CheckMaintenanceServerStatusJob` --call--> `RevertServersMaintenanceDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckMaintenanceServerStatusJob.java:10`
- `RevertServersMaintenanceDelegate` --call--> `ServerStateService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:21`
- `ServerStateService` --call--> `DPoolConfig` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/service/ServerStateService.java:19`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.RevertServersMaintenanceDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservation
  --persist--> table:reservation
```

- `CheckMaintenanceServerStatusJob` --call--> `RevertServersMaintenanceDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckMaintenanceServerStatusJob.java:10`
- `RevertServersMaintenanceDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:22`
- `ReservationService` --call--> `EReservation` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:28`
- `EReservation` --persist--> `table:reservation` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservation.java:10`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.RevertServersMaintenanceDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `CheckMaintenanceServerStatusJob` --call--> `RevertServersMaintenanceDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckMaintenanceServerStatusJob.java:10`
- `RevertServersMaintenanceDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:22`
- `ReservationService` --call--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:29`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.RevertServersMaintenanceDelegate
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `CheckMaintenanceServerStatusJob` --call--> `RevertServersMaintenanceDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckMaintenanceServerStatusJob.java:10`
- `RevertServersMaintenanceDelegate` --call--> `DServer` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:18`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.RevertServersMaintenanceDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `CheckMaintenanceServerStatusJob` --call--> `RevertServersMaintenanceDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckMaintenanceServerStatusJob.java:10`
- `RevertServersMaintenanceDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:22`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckMaintenanceServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.RevertServersMaintenanceDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `CheckMaintenanceServerStatusJob` --call--> `RevertServersMaintenanceDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckMaintenanceServerStatusJob.java:10`
- `RevertServersMaintenanceDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/RevertServersMaintenanceDelegate.java:22`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.service.ServerStateService
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `CheckProvisionedServerStatusJob` --call--> `ServerStateService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisionedServerStatusJob.java:21`
- `ServerStateService` --call--> `DPoolConfig` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/service/ServerStateService.java:19`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.service.ServerStateService
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservation
  --persist--> table:reservation
```

- `CheckProvisionedServerStatusJob` --call--> `ServerStateService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisionedServerStatusJob.java:21`
- `ServerStateService` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/service/ServerStateService.java:24`
- `ReservationService` --call--> `EReservation` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:28`
- `EReservation` --persist--> `table:reservation` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservation.java:10`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob
  --call--> rms.unifiedstore.sqlpool.manager.service.ServerStateService
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `CheckProvisionedServerStatusJob` --call--> `ServerStateService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisionedServerStatusJob.java:21`
- `ServerStateService` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/service/ServerStateService.java:24`
- `ReservationService` --call--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:29`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `CheckProvisionedServerStatusJob` --call--> `DServer` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisionedServerStatusJob.java:18`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `CheckProvisionedServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisionedServerStatusJob.java:22`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisionedServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `CheckProvisionedServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisionedServerStatusJob.java:22`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `CheckProvisioningServerStatusJob` --call--> `DPoolConfig` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisioningServerStatusJob.java:16`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-common, sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.common.model.mappers.GenericMapper
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DReservationMetadata
  --map--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `CheckProvisioningServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisioningServerStatusJob.java:28`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `GenericMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:9`
- `GenericMapper` --call--> `DReservationMetadata` `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/mappers/GenericMapper.java:7`
- `DReservationMetadata` --map--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMetadataMapper.java:18`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `CheckProvisioningServerStatusJob` --call--> `DServer` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisioningServerStatusJob.java:17`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `CheckProvisioningServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisioningServerStatusJob.java:28`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CheckProvisioningServerStatusJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `CheckProvisioningServerStatusJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CheckProvisioningServerStatusJob.java:28`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservation
  --persist--> table:reservation
```

- `CleanReservationJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CleanReservationJob.java:17`
- `ReservationService` --call--> `EReservation` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:28`
- `EReservation` --persist--> `table:reservation` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservation.java:10`

### `rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `CleanReservationJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CleanReservationJob.java:17`
- `ReservationService` --call--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:29`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `CleanReservationJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CleanReservationJob.java:17`
- `ReservationService` --call--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:30`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `CleanReservationJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CleanReservationJob.java:17`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.CleanReservationJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `CleanReservationJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/CleanReservationJob.java:17`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservation
  --persist--> table:reservation
```

- `ProcessPendingReservationsJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ProcessPendingReservationsJob.java:10`
- `ReservationService` --call--> `EReservation` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:28`
- `EReservation` --persist--> `table:reservation` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservation.java:10`

### `rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `ProcessPendingReservationsJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ProcessPendingReservationsJob.java:10`
- `ReservationService` --call--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:29`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `ProcessPendingReservationsJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ProcessPendingReservationsJob.java:10`
- `ReservationService` --call--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:30`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `ProcessPendingReservationsJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ProcessPendingReservationsJob.java:10`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ProcessPendingReservationsJob
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `ProcessPendingReservationsJob` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ProcessPendingReservationsJob.java:10`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-provision, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob
  --call--> rms.unifiedstore.sqlpool.provision.ResourceManagementClientFactory
  --call--> rms.unifiedstore.sqlpool.provision.cloudservices.ResourceManagementClientCS
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `ReconcileServersWithProvidersJob` --call--> `ResourceManagementClientFactory` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ReconcileServersWithProvidersJob.java:16`
- `ResourceManagementClientFactory` --call--> `ResourceManagementClientCS` `sql-pool/sql-pool-provision/src/main/java/RMS/UnifiedStore/sqlpool/provision/ResourceManagementClientFactory.java:8`
- `ResourceManagementClientCS` --call--> `DPoolConfig` `sql-pool/sql-pool-provision/src/main/java/RMS/UnifiedStore/sqlpool/provision/cloudservices/ResourceManagementClientCS.java:15`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-common, sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.common.model.mappers.GenericMapper
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DReservationMetadata
  --map--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `ReconcileServersWithProvidersJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ReconcileServersWithProvidersJob.java:19`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `GenericMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:9`
- `GenericMapper` --call--> `DReservationMetadata` `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/mappers/GenericMapper.java:7`
- `DReservationMetadata` --map--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMetadataMapper.java:18`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `ReconcileServersWithProvidersJob` --call--> `DServer` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ReconcileServersWithProvidersJob.java:13`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `ReconcileServersWithProvidersJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ReconcileServersWithProvidersJob.java:19`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.ReconcileServersWithProvidersJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `ReconcileServersWithProvidersJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/ReconcileServersWithProvidersJob.java:19`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.RetryFailedDeleteServersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-provision, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.RetryFailedDeleteServersJob
  --call--> rms.unifiedstore.sqlpool.provision.ResourceManagementClientFactory
  --call--> rms.unifiedstore.sqlpool.provision.cloudservices.ResourceManagementClientCS
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `RetryFailedDeleteServersJob` --call--> `ResourceManagementClientFactory` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/RetryFailedDeleteServersJob.java:15`
- `ResourceManagementClientFactory` --call--> `ResourceManagementClientCS` `sql-pool/sql-pool-provision/src/main/java/RMS/UnifiedStore/sqlpool/provision/ResourceManagementClientFactory.java:8`
- `ResourceManagementClientCS` --call--> `DPoolConfig` `sql-pool/sql-pool-provision/src/main/java/RMS/UnifiedStore/sqlpool/provision/cloudservices/ResourceManagementClientCS.java:15`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.RetryFailedDeleteServersJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-provision, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.RetryFailedDeleteServersJob
  --call--> rms.unifiedstore.sqlpool.provision.ResourceManagementClientFactory
  --call--> rms.unifiedstore.sqlpool.provision.cloudservices.ResourceManagementClientCS
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `RetryFailedDeleteServersJob` --call--> `ResourceManagementClientFactory` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/RetryFailedDeleteServersJob.java:15`
- `ResourceManagementClientFactory` --call--> `ResourceManagementClientCS` `sql-pool/sql-pool-provision/src/main/java/RMS/UnifiedStore/sqlpool/provision/ResourceManagementClientFactory.java:8`
- `ResourceManagementClientCS` --call--> `DServer` `sql-pool/sql-pool-provision/src/main/java/RMS/UnifiedStore/sqlpool/provision/cloudservices/ResourceManagementClientCS.java:16`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.ProcessServerHintsDelegate
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DPoolConfig
  --map--> rms.unifiedstore.sqlpool.dal.entities.EPoolConfig
  --persist--> table:pool_config
```

- `TrackServersUsageJob` --call--> `ProcessServerHintsDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:11`
- `ProcessServerHintsDelegate` --call--> `DPoolConfig` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/ProcessServerHintsDelegate.java:10`
- `DPoolConfig` --map--> `EPoolConfig` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DPoolConfigMapper.java:30`
- `EPoolConfig` --persist--> `table:pool_config` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EPoolConfig.java:9`

### `rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.MetricsCalculatorDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservation
  --persist--> table:reservation
```

- `TrackServersUsageJob` --call--> `MetricsCalculatorDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:10`
- `MetricsCalculatorDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/MetricsCalculatorDelegate.java:12`
- `ReservationService` --call--> `EReservation` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:28`
- `EReservation` --persist--> `table:reservation` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservation.java:10`

### `rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.MetricsCalculatorDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `TrackServersUsageJob` --call--> `MetricsCalculatorDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:10`
- `MetricsCalculatorDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/MetricsCalculatorDelegate.java:12`
- `ReservationService` --call--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:29`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.MetricsCalculatorDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `TrackServersUsageJob` --call--> `MetricsCalculatorDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:10`
- `MetricsCalculatorDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/MetricsCalculatorDelegate.java:12`
- `ReservationService` --call--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:30`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.MetricsCalculatorDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `TrackServersUsageJob` --call--> `MetricsCalculatorDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:10`
- `MetricsCalculatorDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/MetricsCalculatorDelegate.java:12`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.TrackServersUsageJob
  --call--> rms.unifiedstore.sqlpool.manager.delegate.MetricsCalculatorDelegate
  --call--> rms.unifiedstore.sqlpool.service.services.ReservationService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `TrackServersUsageJob` --call--> `MetricsCalculatorDelegate` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/TrackServersUsageJob.java:10`
- `MetricsCalculatorDelegate` --call--> `ReservationService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/delegate/MetricsCalculatorDelegate.java:12`
- `ReservationService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ReservationService.java:33`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-common, sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.common.model.mappers.GenericMapper
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DReservationMetadata
  --map--> rms.unifiedstore.sqlpool.dal.entities.EReservationMetadata
  --persist--> table:reservation_metadata
```

- `WriteServerResourceUsageLogJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/WriteServerResourceUsageLogJob.java:20`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `GenericMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:9`
- `GenericMapper` --call--> `DReservationMetadata` `sql-pool/sql-pool-common/src/main/java/RMS/UnifiedStore/sqlpool/common/model/mappers/GenericMapper.java:7`
- `DReservationMetadata` --map--> `EReservationMetadata` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DReservationMetadataMapper.java:18`
- `EReservationMetadata` --persist--> `table:reservation_metadata` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EReservationMetadata.java:7`

### `rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `WriteServerResourceUsageLogJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/WriteServerResourceUsageLogJob.java:20`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:10`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

### `rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerResourceUsageLog
  --persist--> table:server_resource_usage_log
```

- `WriteServerResourceUsageLogJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/WriteServerResourceUsageLogJob.java:20`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerResourceUsageLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:11`
- `EServerResourceUsageLog` --persist--> `table:server_resource_usage_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerResourceUsageLog.java:5`

### `rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.WriteServerResourceUsageLogJob
  --call--> rms.unifiedstore.sqlpool.service.services.ServerService
  --call--> rms.unifiedstore.sqlpool.service.mappers.DServerMapper
  --call--> rms.unifiedstore.sqlpool.dal.entities.EServerStatusLog
  --persist--> table:server_status_log
```

- `WriteServerResourceUsageLogJob` --call--> `ServerService` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/WriteServerResourceUsageLogJob.java:20`
- `ServerService` --call--> `DServerMapper` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/services/ServerService.java:21`
- `DServerMapper` --call--> `EServerStatusLog` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:12`
- `EServerStatusLog` --persist--> `table:server_status_log` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServerStatusLog.java:7`

### `scheduler`

_schedule, medium confidence, modules: sql-pool/sql-pool-dal, sql-pool/sql-pool-manager, sql-pool/sql-pool-service_

```
rms.unifiedstore.sqlpool.manager.jobs.AbstractJob
  --call--> rms.unifiedstore.sqlpool.common.model.domain.DServer
  --map--> rms.unifiedstore.sqlpool.dal.entities.EServer
  --persist--> table:server
```

- `AbstractJob` --call--> `DServer` `sql-pool/sql-pool-manager/src/main/java/RMS/UnifiedStore/sqlpool/manager/jobs/AbstractJob.java:18`
- `DServer` --map--> `EServer` `sql-pool/sql-pool-service/src/main/java/RMS/UnifiedStore/sqlpool/service/mappers/DServerMapper.java:36`
- `EServer` --persist--> `table:server` `sql-pool/sql-pool-dal/src/main/java/RMS/UnifiedStore/sqlpool/dal/entities/EServer.java:11`

## What is not traced

- **Runtime dependency injection.** The object graph the application assembles at startup is decided from types, not imports. What is reported here is the *declared* wiring; the runtime graph is a superset CDP cannot see.
- **Dynamic dispatch.** A call through an interface produces an edge to the interface. Implementations are candidates, not hops.
- **Reflection and string-keyed lookup.** Detected as a risk marker on the containing symbol, never traced through.
- **What the data means.** CDP maps where data goes, not what it is. It will not tell you whether `capacity_percent` is a fraction or a percentage.
