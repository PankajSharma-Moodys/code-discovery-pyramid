# `exposure-snapshot/snapshot-filter-query-service`

19 tracked files, 2,217 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-filter-query-service`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `exposure-snapshot/ods-domain-data` (3 refs), `exposure-snapshot/snapshot-common` (53 refs)

**Imported by:** `exposure-snapshot/snapshot-api` (5 refs), `exposure-snapshot/snapshot-workflow-service` (1 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `IdentifierValidator` | interface | 2 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/IdentifierValidator.java:10` |
| `ParserService` | interface | 2 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/ParserService.java:13` |
| `ParserServiceImpl` | class | 2 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/ParserServiceImpl.java:30` |
| `DomainIdentifierValidator` | class | 1 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/DomainIdentifierValidator.java:20` |
| `IdentifierValidatorMode` | enum | 1 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/IdentifierValidatorMode.java:3` |
| `FloodZoneParserListeners` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/FloodZoneParserListeners.java:12` |
| `YearBuiltListeners` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/YearBuiltListeners.java:12` |
| `ConditionVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ConditionVisitor.java:11` |
| `ExpressionVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ExpressionVisitor.java:13` |
| `IdentifierVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/IdentifierVisitor.java:14` |
| `InListVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/InListVisitor.java:14` |
| `MatchingConditionVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/MatchingConditionVisitor.java:11` |
| `RelationalConditionVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/RelationalConditionVisitor.java:16` |
| `SortByVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/SortByVisitor.java:13` |
| `SortListVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/SortListVisitor.java:11` |
| `ValueExpVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ValueExpVisitor.java:10` |
| `ValueVisitor` | class | 0 | `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/visitors/ValueVisitor.java:20` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-filter-query-service` | 19 | 2,217 | structural only |
