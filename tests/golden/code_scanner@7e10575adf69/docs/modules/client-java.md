# `client-java`

3 tracked files, 193 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/client-java`. Facts about the files in those scopes are missing, not absent.

> **Generated module.** 3 tracked file(s) against 420 on disk. Its sources are produced at build time and are invisible to git, so nothing below describes them.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** nothing in this repository

## Entry points

- AutomationDebugTool declares a process entry point in client-java/uds-client-integration-tests; it is one of the repository's separately-startable units. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/AutomationDebugTool.java:81`
- PipelineTestRunner declares a process entry point in client-java/uds-client-integration-tests; it is one of the repository's separately-startable units. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/PipelineTestRunner.java:15`

## Side effects

- client-java/client-core makes outbound HTTP calls, across 3 site(s). — `client-java/client-core/src/main/java/com/rms/unifiedstore/client/core/BaseService.java:38` `client-java/client-core/src/main/java/com/rms/unifiedstore/client/core/ClientFactory.java:4` `client-java/client-core/src/main/java/com/rms/unifiedstore/client/core/Constants.java:3`
- client-java/eih-client makes outbound HTTP calls, across 4 site(s). — `client-java/eih-client/src/main/java/com/rms/eih/DatabaseServiceFactory.java:6` `client-java/eih-client/src/main/java/com/rms/eih/DatabaseServiceImpl.java:17` `client-java/eih-client/src/main/java/com/rms/eih/JobServiceFactory.java:6`
- client-java/uds-client-integration-tests makes outbound HTTP calls, across 6 site(s). — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/ApiKeyTokenGenerator.java:29` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/SmlUserSetupService.java:14` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestHttpClient.java:8`
- client-java/uds-client makes outbound HTTP calls, across 47 site(s). — `client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminServiceFactory.java:5` `client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminServiceImpl.java:14` `client-java/uds-client/src/main/java/com/rms/unifiedstore/AnalysisRegisterServiceFactory.java:6`

## Dependencies (stated)

- client-java holds 3 git-tracked file(s) against 420 on disk. Its contents are generated at build time, so they are invisible to a git-based inventory and are described by the build contract rather than read. — `client-java/pom.xml:1`
- client-java/eih-client imports client-java/client-core at 28 distinct sites. — `client-java/eih-client/src/main/java/com/rms/eih/DatabaseService.java:4` `client-java/eih-client/src/main/java/com/rms/eih/DatabaseService.java:5`
- client-java/uds-client imports client-java/client-core at 247 distinct sites. — `client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminService.java:3` `client-java/uds-client/src/main/java/com/rms/unifiedstore/AdminServiceFactory.java:3`
- client-java/uds-client imports exposure-snapshot/ods-domain-data at 2 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client/src/main/java/com/rms/unifiedstore/ResultRegisterServiceImpl.java:20` `client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java:24`
- client-java/uds-client imports exposure-snapshot/snapshot-sdk at 2 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client/src/main/java/com/rms/unifiedstore/ResultRegisterServiceImpl.java:20` `client-java/uds-client/src/main/java/com/rms/unifiedstore/UnifiedStoreClientImpl.java:24`
- client-java/uds-client-integration-tests imports client-java/client-core at 64 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/ApiKeyTokenGenerator.java:12` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/ApiKeyTokenGenerator.java:13`
- client-java/uds-client-integration-tests imports client-java/eih-client at 2 distinct sites. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/DataBridgeRegistrationTests.java:5` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/DataBridgeRegistrationTests.java:6`
- client-java/uds-client-integration-tests imports client-java/uds-client at 170 distinct sites. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/ServiceApiTestHelper.java:13`
- client-java/uds-client-integration-tests imports exposure-snapshot/download-exposure at 9 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/CatalogAnalysisTests.java:14`
- client-java/uds-client-integration-tests imports exposure-snapshot/snapshot-common at 9 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/CatalogAnalysisTests.java:14`
- client-java/uds-client-integration-tests imports exposure-snapshot/snapshot-legacy/snapshot-legacy-core at 9 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/CatalogAnalysisTests.java:14`
- client-java/uds-client-integration-tests imports exposure-snapshot/snapshot-legacy/snapshot-legacy-task at 9 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/CatalogAnalysisTests.java:14`
- client-java/uds-client-integration-tests imports exposure-snapshot/snapshot-sdk at 9 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/CatalogAnalysisTests.java:14`
- client-java/uds-client-integration-tests imports exposure-snapshot/snapshot-smoketest at 9 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/common/TestContext.java:7` `client-java/uds-client-integration-tests/src/test/java/com/rms/unifiedstore/test/automation/serviceapi/tests/CatalogAnalysisTests.java:14`

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/client-java` | 3 | 193 | structural only |
