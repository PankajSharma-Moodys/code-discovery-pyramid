# `sql-pool/sql-pool-integrationtest`

85 tracked files, 28,758 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/sql-pool/sql-pool-integrationtest/(files+5)`, `root/sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/(files)`, `root/sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `sql-pool/sql-pool-common` (78 refs), `sql-pool/sql-pool-dal` (7 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AbstractIntegrationTest` | class | 41 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/AbstractIntegrationTest.java:16` |
| `ItConfig` | class | 30 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/ItConfig.java:11` |
| `ItDatabase` | class | 30 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/ItDatabase.java:20` |
| `RawHttp` | class | 25 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/RawHttp.java:30` |
| `ServerFixture` | class | 23 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/fixtures/ServerFixture.java:23` |
| `PoolFixture` | class | 22 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/fixtures/PoolFixture.java:26` |
| `S2STokens` | class | 20 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/S2STokens.java:16` |
| `ReservationFixture` | class | 14 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/fixtures/ReservationFixture.java:26` |
| `ComposeCli` | class | 13 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/ComposeCli.java:33` |
| `FixtureScope` | class | 12 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/fixtures/FixtureScope.java:31` |
| `SqlPoolApi` | class | 11 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/SqlPoolApi.java:15` |
| `ManagerWindow` | class | 10 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/ManagerWindow.java:69` |
| `ContainerLogs` | class | 7 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/ContainerLogs.java:20` |
| `RouteCatalog` | class | 4 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/RouteCatalog.java:36` |
| `ServiceConfigFile` | class | 3 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/ServiceConfigFile.java:19` |
| `HealthGate` | class | 2 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/HealthGate.java:20` |
| `FixtureIds` | class | 2 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/fixtures/FixtureIds.java:23` |
| `SchemaBaseline` | class | 2 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/schema/SchemaBaseline.java:25` |
| `SchemaDiff` | class | 2 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/schema/SchemaDiff.java:28` |
| `SchemaSnapshot` | class | 2 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/schema/SchemaSnapshot.java:53` |
| `QuartzJobs` | class | 2 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/QuartzJobs.java:18` |
| `S2SClaimTokens` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/S2SClaimTokens.java:42` |
| `EntityMapping` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/schema/EntityMapping.java:46` |
| `CsStub` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/CsStub.java:35` |
| `JobSchedule` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/JobSchedule.java:36` |
| `Phase24Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase24Arrangement.java:54` |
| `Phase24Handoff` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase24Handoff.java:34` |
| `Phase25Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase25Arrangement.java:82` |
| `Phase26Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase26Arrangement.java:110` |
| `Phase27Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase27Arrangement.java:81` |
| `Phase28Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase28Arrangement.java:110` |
| `Arm` | record | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase28Arrangement.java:140` |
| `Phase29Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase29Arrangement.java:110` |
| `Arm` | record | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase29Arrangement.java:139` |
| `Phase30Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase30Arrangement.java:112` |
| `Arm` | record | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase30Arrangement.java:152` |
| `Phase31Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase31Arrangement.java:129` |
| `Arm` | record | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase31Arrangement.java:167` |
| `Phase32Arrangement` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/Phase32Arrangement.java:85` |
| `PoisonRows` | class | 1 | `sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring/PoisonRows.java:30` |

_17 more; use `cdp query module sql-pool/sql-pool-integrationtest`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/sql-pool/sql-pool-integrationtest/(files+5)` | 23 | 3,194 | structural only |
| `root/sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/(files)` | 42 | 21,087 | structural only |
| `root/sql-pool/sql-pool-integrationtest/src/test/java/rms/unifiedstore/sqlpool/integrationtest/support/wiring` | 20 | 4,477 | structural only |
