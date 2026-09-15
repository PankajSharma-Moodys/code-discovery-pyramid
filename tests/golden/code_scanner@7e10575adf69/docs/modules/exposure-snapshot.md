# `exposure-snapshot`

49 tracked files, 247,920 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/(files+1)`, `root/exposure-snapshot/domain-data-migration/migrations`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** nothing in this repository

## Entry points

- GenerateExposureSchemaFromParquetFiles declares a process entry point in exposure-snapshot/snapshot-developer-utils; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-developer-utils/src/main/java/GenerateExposureSchemaFromParquetFiles.java:143`
- DeleteSnapshotTask declares a process entry point in exposure-snapshot/snapshot-task-delete; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:126`
- AccountSnapshotEngine declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/engine/AccountSnapshotEngine.java:9`
- PortfolioSnapshotEngine declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/engine/PortfolioSnapshotEngine.java:9`
- SnapshotEngine declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/engine/SnapshotEngine.java:14`
- ExposureBundleServiceIT declares a process entry point in exposure-snapshot/entity-variation-task; it is one of the repository's separately-startable units. — `exposure-snapshot/entity-variation-task/src/test/java/com/rms/unifiedstore/entityvariation/integration/ExposureBundleServiceIT.java:17`
- SnapshotPartitionTask declares a process entry point in exposure-snapshot/snapshot-legacy/snapshot-legacy-partition; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition/src/main/java/com/rms/unifiedstore/partition/SnapshotPartitionTask.java:10`
- APIApplication declares a process entry point in exposure-snapshot/snapshot-api; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:102`
- GetS2STokenApp declares a process entry point in exposure-snapshot/snapshot-api; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/GetS2STokenApp.java:10`
- SnapshotApplication declares a process entry point in exposure-snapshot/snapshot-task-create; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/SnapshotApplication.java:25`
- TransformEdmTask declares a process entry point in exposure-snapshot/snapshot-legacy/snapshot-legacy-transform; it is one of the repository's separately-startable units. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform/src/main/java/com/rms/unifiedstore/transform/TransformEdmTask.java:10`
- exposure-snapshot/domain-data-migration declares a process entry point in exposure-snapshot; it is one of the repository's separately-startable units. — `exposure-snapshot/domain-data-migration/Dockerfile:30`
- DELETE /tenant/{tenantId} is served by TenantProvisioningResource#deleteProvisionsForTenant in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/TenantProvisioningResource.java:140`
- DELETE /{variationId} is served by ExposureVariationsResource#deleteExposureVariationByVariationId in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureVariationsResource.java:218`
- GET / is served by ExposureBundlesResource#getExposureBundleTableSets in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:570`
- GET /openapi is served by SwaggerResource#get in exposure-snapshot/swagger-resource. — `exposure-snapshot/swagger-resource/src/main/java/com/rms/utils/swagger/SwaggerResource.java:20`
- GET /tenant/{tenantId} is served by TenantProvisioningResource#getProvisionStatusForTenant in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/TenantProvisioningResource.java:54`
- GET /{bundleId} is served by ExposureBundlesResource#getExposureBundle in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:685`
- GET /{bundleId}/metrics is served by ExposureBundlesResource#getExposureBundleMetrics in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:847`
- GET /{bundleId}/tablesets is served by ExposureBundlesResource#getExposureBundleTableSets in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:763`
- GET /{jobId} is served by VariationJobsResource#getJob in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:263`
- GET /{variationId} is served by ExposureVariationsResource#getExposureVariation in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureVariationsResource.java:166`
- GET internal/variation/v1/exposurevariations is served by InternalVariationResource#getExposureVariations in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:196`
- GET internal/variation/v1/exposurevariations/admin is served by InternalVariationResource#getExposureVariationsAsAdmin in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:281`
- GET internal/variation/v1/exposurevariations/{variationId} is served by InternalVariationResource#getExposureVariation in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:55`
- GET internal/variation/v1/exposurevariations/{variationId}/admin is served by InternalVariationResource#getExposureVariationAsAdmin in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/InternalVariationResource.java:129`
- GET v1/{tenantId}/exposures is served by EntityVariationResource#getEntityVariations in exposure-snapshot/snapshot-api (declared via the constant ${ApiConstants.SNAPSHOT_PATH}). — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:521` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29`
- GET v1/{tenantId}/exposures//{entityName}/variationjobs/{variationJobId} is served by EntityVariationResource#getEntityVariationJob in exposure-snapshot/snapshot-api (declared via the constant ${ApiConstants.SNAPSHOT_PATH}/${ApiConstants.VARIATION_JOBS_PATH}). — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:405` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:35`
- PATCH /{jobId} is served by VariationJobsResource#updateJob in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:313`
- POST / is served by ExposureBundlesResource#createExposureBundle in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:103`
- POST /tenant/{tenantId} is served by TenantProvisioningResource#provisionForTenant in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/TenantProvisioningResource.java:101`
- POST /upload is served by ExposureBundlesResource#prepareUploadExposureBundle in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:187`
- POST /{bundleId}/tableset is served by ExposureBundlesResource#createExposureBundleTableSet in exposure-snapshot/snapshot-api. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:255`
- POST v1/{tenantId}/exposures is served by EntityVariationResource#postEntityVariation in exposure-snapshot/snapshot-api (declared via the constant ${ApiConstants.SNAPSHOT_PATH}). — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:157` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29`
- POST v1/{tenantId}/exposures//live-variations is served by EntityVariationResource#postLiveEntityVariations in exposure-snapshot/snapshot-api (declared via the constant ${ApiConstants.SNAPSHOT_PATH}/${ApiConstants.LIVE_VARIATION_PATH}). — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:816` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:29` `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/constants/ApiConstants.java:48`

## Data models

- Table 'countcheck' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V022__DomainProcedures.sql:482`
- Table 'domain_data.' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V021__InsertCommonData.sql:1`
- Table 'domain_data.acodscbe' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13451`
- Table 'domain_data.acodscca' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13511`
- Table 'domain_data.acodscdk' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13599`
- Table 'domain_data.acodscfr' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13628`
- Table 'domain_data.acodscgb' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13658`
- Table 'domain_data.acodscie' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13481`
- Table 'domain_data.acodscit' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13570`
- Table 'domain_data.acodsctr' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13687`
- Table 'domain_data.acodscus' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13541`
- Table 'domain_data.acodsczz' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13716`
- Table 'domain_data.activestatus' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V036__Insert_DomainTables2.sql:39`
- Table 'domain_data.addresstype' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V036__Insert_DomainTables2.sql:59`
- Table 'domain_data.attributetype' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:21`
- Table 'domain_data.bipreparedness' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V038__Insert_DomainTables4.sql:32`
- Table 'domain_data.biredundancy' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V038__Insert_DomainTables4.sql:39`
- Table 'domain_data.contentgrade' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V037__Insert_DomainTables3.sql:16`
- Table 'domain_data.country' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V026__Create_Country_VulNames_Tables.sql:55`
- Table 'domain_data.countylevel' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V026__Create_Country_VulNames_Tables.sql:335`
- Table 'domain_data.covbase' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:26954`
- Table 'domain_data.csodscau' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:11354`
- Table 'domain_data.csodscca' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:11550`
- Table 'domain_data.csodscus' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:11746`
- Table 'domain_data.csvccau' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V012__Insert_CS_DATA.sql:7338`
- Table 'domain_data.csvccca' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V012__Insert_CS_DATA.sql:19375`
- Table 'domain_data.csvccus' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V012__Insert_CS_DATA.sql:1`
- Table 'domain_data.csvoccau' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V012__Insert_CS_DATA.sql:7457`
- Table 'domain_data.csvoccca' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V012__Insert_CS_DATA.sql:396`
- Table 'domain_data.csvoccus' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V012__Insert_CS_DATA.sql:12307`
- Table 'domain_data.currency' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:72`
- Table 'domain_data.datasourcetype' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V035__ReloadTables.sql:245`
- Table 'domain_data.enginetype' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:26929`
- Table 'domain_data.entity' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V021__InsertCommonData.sql:5`
- Table 'domain_data.entityattributes' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V021__InsertCommonData.sql:209`
- Table 'domain_data.entityattributesmetadata' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V021__InsertCommonData.sql:3427`
- Table 'domain_data.entitytodatabasemapping' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V021__InsertCommonData.sql:17326`
- Table 'domain_data.entitytype' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V021__InsertCommonData.sql:17458`
- Table 'domain_data.eqodscad' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5557`
- Table 'domain_data.eqodscar' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5646`
- Table 'domain_data.eqodscat' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5736`
- Table 'domain_data.eqodscau' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5825`
- Table 'domain_data.eqodscbe' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5916`
- Table 'domain_data.eqodscbg' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6005`
- Table 'domain_data.eqodscbo' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6094`
- Table 'domain_data.eqodscbr' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6184`
- Table 'domain_data.eqodscbz' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6274`
- Table 'domain_data.eqodscca' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6364`
- Table 'domain_data.eqodsccb' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6509`
- Table 'domain_data.eqodscch' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6560`
- Table 'domain_data.eqodsccl' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6649`
- Table 'domain_data.eqodsccn' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6738`
- Table 'domain_data.eqodscco' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6827`
- Table 'domain_data.eqodsccr' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:6917`
- Table 'domain_data.eqodscde' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:7056`
- Table 'domain_data.eqodscec' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:7146`
- Table 'domain_data.eqodsces' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:7324`
- Table 'domain_data.eqodscfr' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:7505`
- Table 'domain_data.eqodscgb' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:7595`
- Table 'domain_data.eqodscgr' is written from sql in exposure-snapshot. — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:7685`
- _... and 186 more; use `cdp query claims --kind data_model --module exposure-snapshot`_

## Configuration

- Configuration key 'DEBIAN_FRONTEND' is read at 1 site(s) in exposure-snapshot/snapshot-legacy/snapshot-legacy-transform. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform/Dockerfile:3`
- Configuration key 'FLYWAY_CMD_VERSION' is read at 3 site(s) in (root), exposure-snapshot, exposure-snapshot/snapshot-migration. — `exposure-snapshot/domain-data-migration/Dockerfile:11` `exposure-snapshot/snapshot-migration/Dockerfile:16` `service-api/docker/Dockerfile:5`
- Configuration key 'JAVA_ARGS' is read at 1 site(s) in exposure-snapshot/snapshot-migration. — `exposure-snapshot/snapshot-migration/Dockerfile:36`
- Configuration key 'JAVA_TOOL_OPTIONS' is read at 2 site(s) in exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation, exposure-snapshot/snapshot-legacy/snapshot-legacy-transform. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-accumulation/Dockerfile:3` `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform/Dockerfile:4`
- Configuration key 'LANG' is read at 2 site(s) in exposure-snapshot/entity-variation-task, exposure-snapshot/snapshot-task-delete. — `exposure-snapshot/entity-variation-task/Dockerfile:7` `exposure-snapshot/snapshot-task-delete/Dockerfile:5`
- Configuration key 'LANGUAGE' is read at 2 site(s) in exposure-snapshot/entity-variation-task, exposure-snapshot/snapshot-task-delete. — `exposure-snapshot/entity-variation-task/Dockerfile:8` `exposure-snapshot/snapshot-task-delete/Dockerfile:6`
- Configuration key 'LC_ALL' is read at 2 site(s) in exposure-snapshot/entity-variation-task, exposure-snapshot/snapshot-task-delete. — `exposure-snapshot/entity-variation-task/Dockerfile:9` `exposure-snapshot/snapshot-task-delete/Dockerfile:7`
- Configuration key 'WORKINGDIR' is read at 1 site(s) in exposure-snapshot/snapshot-smoketest. — `exposure-snapshot/snapshot-smoketest/Dockerfile:3`
- Configuration key 'com' is read at 4 site(s) in exposure-snapshot/download-exposure, exposure-snapshot/snapshot-legacy/snapshot-legacy-partition, exposure-snapshot/snapshot-legacy/snapshot-legacy-task, exposure-snapshot/snapshot-task-delete. — `exposure-snapshot/download-exposure/Dockerfile:5` `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition/Dockerfile:5` `exposure-snapshot/snapshot-legacy/snapshot-legacy-task/Dockerfile:4`

## Side effects

- exposure-snapshot/entity-variation-task makes outbound HTTP calls, across 1 site(s). — `exposure-snapshot/entity-variation-task/src/main/java/com/rms/unifiedstore/entityvariation/helper/GeoHazHelper.java:25`
- exposure-snapshot/snapshot-api makes outbound HTTP calls, across 1 site(s). — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:68`
- exposure-snapshot/snapshot-api emits metrics to an observability sink, across 7 site(s). — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:11` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/EntityVariationResource.java:29` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:15`
- exposure-snapshot/snapshot-common emits metrics to an observability sink, across 1 site(s). — `exposure-snapshot/snapshot-common/src/main/java/com/rms/unifiedstore/snapshot/common/database/ManagedDataSourceFactoryImpl.java:3`

## Ownership

- The schema for 'domain_data.' is owned by exposure-snapshot, defined across 3 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V009__CommonDomainTables.sql:7` `exposure-snapshot/domain-data-migration/migrations/V035__ReloadTables.sql:254` `exposure-snapshot/domain-data-migration/migrations/V037__Insert_DomainTables3.sql:30`
- The schema for 'domain_data.acodscbe' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13444`
- The schema for 'domain_data.acodscca' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13505`
- The schema for 'domain_data.acodscdk' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13593`
- The schema for 'domain_data.acodscfr' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13622`
- The schema for 'domain_data.acodscgb' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13652`
- The schema for 'domain_data.acodscie' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13475`
- The schema for 'domain_data.acodscit' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13564`
- The schema for 'domain_data.acodsctr' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13681`
- The schema for 'domain_data.acodscus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13535`
- The schema for 'domain_data.acodsczz' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:13710`
- The schema for 'domain_data.activestatus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V036__Insert_DomainTables2.sql:34`
- The schema for 'domain_data.acvccbe' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:7`
- The schema for 'domain_data.acvccca' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:28`
- The schema for 'domain_data.acvccdk' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:49`
- The schema for 'domain_data.acvccfr' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:70`
- The schema for 'domain_data.acvccgb' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:90`
- The schema for 'domain_data.acvccie' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:111`
- The schema for 'domain_data.acvccit' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:132`
- The schema for 'domain_data.acvcctr' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:153`
- The schema for 'domain_data.acvccus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:174`
- The schema for 'domain_data.acvcczz' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:195`
- The schema for 'domain_data.acvoccbe' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:216`
- The schema for 'domain_data.acvoccca' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:236`
- The schema for 'domain_data.acvoccdk' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:256`
- The schema for 'domain_data.acvoccfr' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:276`
- The schema for 'domain_data.acvoccgb' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:295`
- The schema for 'domain_data.acvoccie' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:315`
- The schema for 'domain_data.acvoccit' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:335`
- The schema for 'domain_data.acvocctr' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:355`
- The schema for 'domain_data.acvoccus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:375`
- The schema for 'domain_data.acvocczz' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V001__ACTables.sql:395`
- The schema for 'domain_data.addresstype' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V036__Insert_DomainTables2.sql:53`
- The schema for 'domain_data.attributetype' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:7`
- The schema for 'domain_data.bipreparedness' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V038__Insert_DomainTables4.sql:7`
- The schema for 'domain_data.biredundancy' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V038__Insert_DomainTables4.sql:22`
- The schema for 'domain_data.contentgrade' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V037__Insert_DomainTables3.sql:7`
- The schema for 'domain_data.country' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V026__Create_Country_VulNames_Tables.sql:7`
- The schema for 'domain_data.countylevel' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V026__Create_Country_VulNames_Tables.sql:28`
- The schema for 'domain_data.covbase' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:26947`
- The schema for 'domain_data.csodscau' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:11348`
- The schema for 'domain_data.csodscca' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:11544`
- The schema for 'domain_data.csodscus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:11740`
- The schema for 'domain_data.csvccau' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V002__CSTables.sql:7`
- The schema for 'domain_data.csvccca' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V002__CSTables.sql:28`
- The schema for 'domain_data.csvccus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V002__CSTables.sql:49`
- The schema for 'domain_data.csvoccau' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V002__CSTables.sql:70`
- The schema for 'domain_data.csvoccca' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V002__CSTables.sql:91`
- The schema for 'domain_data.csvoccus' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V002__CSTables.sql:112`
- The schema for 'domain_data.currency' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:57`
- The schema for 'domain_data.datasourcetype' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V035__ReloadTables.sql:234`
- The schema for 'domain_data.enginetype' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V033__AddAttributeTypeDomainTable.sql:26899`
- The schema for 'domain_data.entity' is owned by exposure-snapshot, defined across 2 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V009__CommonDomainTables.sql:26` `exposure-snapshot/domain-data-migration/migrations/V035__ReloadTables.sql:7`
- The schema for 'domain_data.entityattributes' is owned by exposure-snapshot, defined across 2 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V009__CommonDomainTables.sql:51` `exposure-snapshot/domain-data-migration/migrations/V035__ReloadTables.sql:275`
- The schema for 'domain_data.entityattributesmetadata' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V009__CommonDomainTables.sql:73`
- The schema for 'domain_data.entitytodatabasemapping' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V009__CommonDomainTables.sql:88`
- The schema for 'domain_data.entitytype' is owned by exposure-snapshot, defined across 2 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V009__CommonDomainTables.sql:101` `exposure-snapshot/domain-data-migration/migrations/V035__ReloadTables.sql:3512`
- The schema for 'domain_data.eqodscad' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5551`
- The schema for 'domain_data.eqodscar' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5640`
- The schema for 'domain_data.eqodscat' is owned by exposure-snapshot, defined across 1 migration(s). — `exposure-snapshot/domain-data-migration/migrations/V039__Insert_ODSC_Tables.sql:5730`
- _... and 366 more; use `cdp query claims --kind ownership --module exposure-snapshot`_

## Naming

- 1 source files declare a package whose text and directory path do not correspond (e.g. directory 'com/rms/unifiedstore/snapshot/common/constants' declares 'package com.rms.unifiedstore.constants'). Any path-to-package inference produces names that match nothing; on a case-insensitive filesystem this is invisible. — `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/constants/CacheConstants.java:3` `sql-pool/sql-pool-api/src/main/java/RMS/UnifiedStore/sqlpool/api/errorhandling/SPMExceptionMapper.java:11`

## Dependencies (stated)

- exposure-snapshot/idempotency-filter imports exposure-snapshot/ods-domain-data at 6 distinct sites. — `exposure-snapshot/idempotency-filter/src/main/java/com/rms/utils/idempotent/feature/IdempotentFeature.java:7` `exposure-snapshot/idempotency-filter/src/main/java/com/rms/utils/idempotent/feature/IdempotentFeature.java:8`
- exposure-snapshot/idempotency-filter imports exposure-snapshot/snapshot-common at 2 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/idempotency-filter/src/main/java/com/rms/utils/idempotent/filter/IdempotentRequestFilter.java:6` `exposure-snapshot/idempotency-filter/src/main/java/com/rms/utils/idempotent/filter/IdempotentResponseFilter.java:10`
- exposure-snapshot/ods-domain-data imports client-java/uds-client at 1 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/services/DomainService.java:6`
- exposure-snapshot/ods-domain-data imports exposure-snapshot/snapshot-common at 13 distinct sites. — `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CacheKeyGeneratorWithVersion.java:3` `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/PooledRedisConfigProvider.java:4`
- exposure-snapshot/ods-domain-data imports exposure-snapshot/snapshot-sdk at 1 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/services/DomainService.java:6`
- exposure-snapshot/snapshot-api imports client-java/client-core at 2 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:20` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/ExposureBundlesResource.java:21`
- exposure-snapshot/snapshot-api imports client-java/uds-client at 33 distinct sites. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotApiValidator.java:12` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotDbHelper.java:3`
- exposure-snapshot/snapshot-api imports exposure-snapshot/idempotency-filter at 3 distinct sites. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:72` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/resources/VariationJobsResource.java:35`
- exposure-snapshot/snapshot-api imports exposure-snapshot/ods-domain-data at 12 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:26` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:27`
- exposure-snapshot/snapshot-api imports exposure-snapshot/snapshot-common at 414 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:52` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:53`
- exposure-snapshot/snapshot-api imports exposure-snapshot/snapshot-filter-query-service at 5 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:22` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:23`
- exposure-snapshot/snapshot-api imports exposure-snapshot/snapshot-legacy/snapshot-legacy-core at 6 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/helper/SnapshotDbHelper.java:3` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/irp/variation/v1/SnapshotApiImpl.java:19`
- exposure-snapshot/snapshot-api imports exposure-snapshot/snapshot-sdk at 25 distinct sites. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:37` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:38`
- exposure-snapshot/snapshot-api imports exposure-snapshot/snapshot-workflow-service at 30 distinct sites. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:66` `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:67`
- exposure-snapshot/snapshot-api imports exposure-snapshot/swagger-resource at 1 distinct sites. — `exposure-snapshot/snapshot-api/src/main/java/com/rms/unifiedstore/snapshot/api/APIApplication.java:73`
- exposure-snapshot/snapshot-developer-utils imports exposure-snapshot/snapshot-common at 4 distinct sites. — `exposure-snapshot/snapshot-developer-utils/src/main/java/GenerateExposureSchemaFromParquetFiles.java:2` `exposure-snapshot/snapshot-developer-utils/src/main/java/GenerateExposureSchemaFromParquetFiles.java:3`
- exposure-snapshot/snapshot-filter-query-service imports exposure-snapshot/ods-domain-data at 3 distinct sites. — `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/DomainIdentifierValidator.java:3` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/DomainIdentifierValidator.java:4`
- exposure-snapshot/snapshot-filter-query-service imports exposure-snapshot/snapshot-common at 53 distinct sites. — `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/DomainIdentifierValidator.java:6` `exposure-snapshot/snapshot-filter-query-service/src/main/java/com/rms/snapshot/filter/service/DomainIdentifierValidator.java:7`
- exposure-snapshot/snapshot-legacy holds 1 git-tracked file(s) against 58 on disk. Its contents are generated at build time, so they are invisible to a git-based inventory and are described by the build contract rather than read. — `exposure-snapshot/snapshot-legacy/pom.xml:1`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-core imports exposure-snapshot/snapshot-common at 3 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/PartitionMatrix.java:3` `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/PartitionMatrix.java:4`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-core imports exposure-snapshot/snapshot-sdk at 2 distinct sites. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/utility/S3Utility.java:3` `exposure-snapshot/snapshot-legacy/snapshot-legacy-core/src/main/java/com/rms/unifiedstore/utility/S3Utility.java:4`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-partition imports exposure-snapshot/snapshot-common at 1 distinct sites. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-partition/src/main/java/com/rms/unifiedstore/partition/SnapshotPartitionTask.java:3`
- exposure-snapshot/snapshot-legacy/snapshot-legacy-transform imports exposure-snapshot/snapshot-common at 1 distinct sites. — `exposure-snapshot/snapshot-legacy/snapshot-legacy-transform/src/main/java/com/rms/unifiedstore/transform/TransformEdmTask.java:3`
- exposure-snapshot/snapshot-sdk imports client-java/client-core at 1 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/UdsSdkHelper.java:10`
- exposure-snapshot/snapshot-sdk imports client-java/uds-client at 12 distinct sites. — `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/ExternalApiCallHelper.java:8` `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/helper/UdsSdkHelper.java:4`
- exposure-snapshot/snapshot-sdk imports exposure-snapshot/snapshot-common at 20 distinct sites. — `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageFactory.java:3` `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/RMSStorageFactory.java:4`
- exposure-snapshot/snapshot-sdk imports exposure-snapshot/snapshot-legacy/snapshot-legacy-core at 1 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-sdk/src/main/java/com/rms/unifiedstore/workflow/EdmQueryService.java:3`
- exposure-snapshot/snapshot-task-create imports client-java/uds-client at 2 distinct sites. — `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/lambda/model/LambdaSnapshotEdmBundleResponse.java:4` `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/lambda/model/LambdaSnapshotEdmBundleResponse.java:5`
- exposure-snapshot/snapshot-task-create imports exposure-snapshot/snapshot-common at 13 distinct sites. — `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/EdmBundleManager.java:7` `exposure-snapshot/snapshot-task-create/src/main/java/com/rms/unifiedstore/snapshot/task/create/EdmBundleManager.java:8`
- exposure-snapshot/snapshot-task-delete imports client-java/uds-client at 1 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:5`
- exposure-snapshot/snapshot-task-delete imports exposure-snapshot/snapshot-common at 8 distinct sites. — `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:5` `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:6`
- exposure-snapshot/snapshot-task-delete imports exposure-snapshot/snapshot-legacy/snapshot-legacy-core at 1 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:5`
- exposure-snapshot/snapshot-task-delete imports exposure-snapshot/snapshot-sdk at 3 distinct sites. — `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:3` `exposure-snapshot/snapshot-task-delete/src/main/java/com/rms/unifiedstore/delete/task/DeleteSnapshotTask.java:4`
- exposure-snapshot/snapshot-workflow-service imports exposure-snapshot/snapshot-common at 23 distinct sites. This edge is NOT declared in the build manifest; it compiles by transitive resolution and will break on a dependency bump. — `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/V2WorkflowConnector.java:6` `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/V2WorkflowConnector.java:7`
- exposure-snapshot/snapshot-workflow-service imports exposure-snapshot/snapshot-filter-query-service at 1 distinct sites. — `exposure-snapshot/snapshot-workflow-service/src/main/java/com/rms/unifiedstore/workflow/WorkflowSearchServiceImpl.java:10`

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/(files+1)` | 8 | 1,069 | structural only |
| `root/exposure-snapshot/domain-data-migration/migrations` | 41 | 246,851 | structural only |
