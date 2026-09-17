# `exposure-snapshot/snapshot-smoketest`

43 tracked files, 4,784 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/snapshot-smoketest/(files+1)`, `root/exposure-snapshot/snapshot-smoketest/src/main/scala`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/client-core` (1 refs), `exposure-snapshot/snapshot-sdk` (6 refs)

**Imported by:** `client-java/uds-client-integration-tests` (9 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation` (6 refs), `exposure-snapshot/snapshot-legacy/snapshot-legacy-task` (1 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `BaseTestResource` | class | 5 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/BaseTestResource.scala:9` |
| `SearchResponse` | class | 3 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/common/SearchResponse.java:5` |
| `PolicyResponse` | class | 2 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:7` |
| `PortfolioAccountResponse` | class | 2 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioAccountResponse.java:8` |
| `TreatyResponse` | class | 2 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/TreatyResponse/TreatyResponse.java:7` |
| `BundlesResourceSuite` | class | 1 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/api/BundlesResourceSuite.scala:15` |
| `PolicyItem` | class | 1 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:239` |
| `PortfolioResponse` | class | 1 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioResponse.java:8` |
| `TreatyItem` | class | 1 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/TreatyResponse/TreatyItem.java:5` |
| `EdmResponseItem` | class | 1 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/edm/EdmResponseItem.java:5` |
| `SmokeTestSuite` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/SmokeTestSuite.scala:5` |
| `OdsAccountTestSuite` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/api/OdsAccountTestSuite.scala:20` |
| `OdsPolicyTestSuite` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/api/OdsPolicyTestSuite.scala:17` |
| `OdsPortfolioTestSuite` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/api/OdsPortfolioTestSuite.scala:21` |
| `OdsTreatyTestSuite` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/api/OdsTreatyTestSuite.scala:16` |
| `AccountItemResponse` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountItemResponse.java:5` |
| `Branch` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountItemResponse.java:147` |
| `Cedant` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountItemResponse.java:164` |
| `Producer` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountItemResponse.java:181` |
| `Underwriter` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountItemResponse.java:198` |
| `AccountMetricsResponse` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountMetricsResponse.java:5` |
| `TotalInsuredValue` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/AccountResponse/AccountMetricsResponse.java:119` |
| `CoverageBase` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:71` |
| `Currency` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:95` |
| `IsFranchiseDeductible` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:119` |
| `LimitGU` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:143` |
| `Lob` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:167` |
| `NewCauseOfLoss` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:191` |
| `Peril` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:215` |
| `Status` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:47` |
| `Structure` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PolicyResponse/PolicyResponse.java:23` |
| `AccountItem` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/AccountItem.java:5` |
| `PortFolioResponseDto` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioResponseDto.scala:3` |
| `PortfolioItem` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioItem.java:5` |
| `PortfolioLocationResponse` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioLocationResponse.java:7` |
| `PortfolioMetricsResponse` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioMetricsResponse.java:5` |
| `SearchItems` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/PortfolioResponse/PortfolioResponseDto.scala:8` |
| `AttachBasis` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/TreatyResponse/TreatyResponse.java:23` |
| `AttachLevel` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/TreatyResponse/TreatyResponse.java:47` |
| `Cedant` | class | 0 | `exposure-snapshot/snapshot-smoketest/src/main/scala/com/rms/unifiedstore/dto/ods/TreatyResponse/TreatyResponse.java:71` |

_11 more; use `cdp query module exposure-snapshot/snapshot-smoketest`._

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/snapshot-smoketest/(files+1)` | 9 | 1,782 | structural only |
| `root/exposure-snapshot/snapshot-smoketest/src/main/scala` | 34 | 3,002 | structural only |
