# Unknowns — the tribal-knowledge inventory

Every question this run could not answer, with the anchor that raised it. This is the list to take to the incumbent team before they leave. A gap here is *output*, not failure: the alternative is a document that asserts a plausible answer, and a reader who cannot tell the difference.

> **Coverage: 0.0%** — 0 of 4728 tracked files are in scopes that completed. Everything absent from this document may be absent because it was never examined. Incomplete scopes: `root/(.github+3)`, `root/(build+5)`, `root/(files)`, `root/.claude`, `root/.cursor`, `root/automation`, `root/automation/api-automation/(files+10)`, `root/automation/api-automation/src/main/java/com/rms/uds/tests`.

## `root`

- **What contract does automation actually publish?**
  - _why unresolved:_ 42 of its 44 files are untracked and generated at build time, so its public surface cannot be read from the repository.
- **What contract does client-java actually publish?**
  - _why unresolved:_ 417 of its 420 files are untracked and generated at build time, so its public surface cannot be read from the repository.
- **What contract does exposure-snapshot/snapshot-legacy actually publish?**
  - _why unresolved:_ 57 of its 58 files are untracked and generated at build time, so its public surface cannot be read from the repository.
- **What contract does sql-pool actually publish?**
  - _why unresolved:_ 457 of its 477 files are untracked and generated at build time, so its public surface cannot be read from the repository.

## Public types with no static reference

No static reference found. Framework-managed entry points are excluded: dependency-injection annotations, HTTP resource registration, scheduled jobs, repositories, entities and generated mappers. These are candidates for review, not dead code (§6.6).

568 candidate(s). These are **not** dead code; any of dependency injection, HTTP resource registration, job discovery or generated implementations makes a naive dead-code claim wrong.

- `RMS.unifiedstore.sqlpool.common.selector.server.AddingCapacityLessThanThresholdStrategyTest` `sql-pool/sql-pool-common/src/test/java/RMS/unifiedstore/sqlpool/common/selector/server/AddingCapacityLessThanThresholdStrategyTest.java:13`
- `com.rms.eih.DatabaseServiceImpl` `client-java/eih-client/src/main/java/com/rms/eih/DatabaseServiceImpl.java:25`
- `com.rms.eih.EihClientImpl` `client-java/eih-client/src/main/java/com/rms/eih/EihClientImpl.java:19`
- `com.rms.snapshot.filter.service.FloodZoneParserListeners` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/FloodZoneParserListeners.java:12`
- `com.rms.snapshot.filter.service.YearBuiltListeners` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/YearBuiltListeners.java:12`
- `com.rms.snapshot.filter.service.visitors.ConditionVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ConditionVisitor.java:11`
- `com.rms.snapshot.filter.service.visitors.ExpressionVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ExpressionVisitor.java:13`
- `com.rms.snapshot.filter.service.visitors.IdentifierVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/IdentifierVisitor.java:14`
- `com.rms.snapshot.filter.service.visitors.InListVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/InListVisitor.java:14`
- `com.rms.snapshot.filter.service.visitors.MatchingConditionVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/MatchingConditionVisitor.java:11`
- `com.rms.snapshot.filter.service.visitors.RelationalConditionVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/RelationalConditionVisitor.java:16`
- `com.rms.snapshot.filter.service.visitors.SortByVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/SortByVisitor.java:13`
- `com.rms.snapshot.filter.service.visitors.SortListVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/SortListVisitor.java:11`
- `com.rms.snapshot.filter.service.visitors.ValueExpVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ValueExpVisitor.java:10`
- `com.rms.snapshot.filter.service.visitors.ValueVisitor` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ValueVisitor.java:20`
- `com.rms.uds.apis.dataCatalog.AccessApi` `automation/api-automation/src/main/java/com/rms/uds/apis/dataCatalog/AccessApi.java:16`
- `com.rms.uds.apis.dataCatalog.EntityApi` `automation/api-automation/src/main/java/com/rms/uds/apis/dataCatalog/EntityApi.java:12`
- `com.rms.uds.bal.dataCatalog.CommonRequest` `automation/api-automation/src/main/java/com/rms/uds/bal/dataCatalog/CommonRequest.java:11`
- `com.rms.uds.bal.dataCatalog.EndpointManager` `automation/api-automation/src/main/java/com/rms/uds/bal/dataCatalog/EndpointManager.java:6`
- `com.rms.uds.bal.dataCatalog.PayloadRepository` `automation/api-automation/src/main/java/com/rms/uds/bal/dataCatalog/PayloadRepository.java:7`
- `com.rms.uds.constants.AutomationConstants` `automation/api-automation/src/main/java/com/rms/uds/constants/AutomationConstants.java:6`
- `com.rms.uds.tests.TestSuiteExecutor` `automation/api-automation/src/main/java/com/rms/uds/tests/TestSuiteExecutor.java:17`
- `com.rms.uds.tests.dataCatalog.AccessApiTest` `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/AccessApiTest.java:45`
- `com.rms.uds.tests.dataCatalog.CatalogApiTest` `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/CatalogApiTest.java:35`
- `com.rms.uds.tests.dataCatalog.CatalogEntitiesCrudTest` `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/CatalogEntitiesCrudTest.java:61`
- `com.rms.uds.tests.dataCatalog.CrudEntitiesTest` `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/CrudEntitiesTest.java:41`
- `com.rms.uds.tests.dataCatalog.SecurableApiTest` `automation/api-automation/src/main/java/com/rms/uds/tests/dataCatalog/SecurableApiTest.java:69`
- `com.rms.uds.tests.managedSql.EdmCrudTest` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/EdmCrudTest.java:31`
- `com.rms.uds.tests.managedSql.SmokeSuite` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:37`
- `com.rms.uds.tests.managedSql.SmokeSuite.ExportDatabaseRequest` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:536`
- `com.rms.uds.tests.managedSql.SmokeSuite.ExportToType` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:378`
- `com.rms.uds.tests.managedSql.SmokeSuite.ImportDatabaseRequest` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:387`
- `com.rms.uds.tests.managedSql.SmokeSuite.ImportEdmRequestv3` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:480`
- `com.rms.uds.tests.managedSql.SmokeSuite.ImportFromType` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:369`
- `com.rms.uds.tests.managedSql.SmokeSuite.Pair` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:344`
- `com.rms.uds.tests.managedSql.SmokeSuite.SmokeSuiteTestResult` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/SmokeSuite.java:1602`
- `com.rms.uds.tests.managedSql.TransientDbCrudTest` `automation/api-automation/src/main/java/com/rms/uds/tests/managedSql/TransientDbCrudTest.java:31`
- `com.rms.uds.util.datacatalog.ApiUtil` `automation/api-automation/src/main/java/com/rms/uds/util/datacatalog/ApiUtil.java:10`
- `com.rms.unifiedstore.AdminService` `client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminService.java:6`
- `com.rms.unifiedstore.AdminServiceFactory` `client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminServiceFactory.java:7`
