# `exposure-snapshot/ods-domain-data`

31 tracked files, 2,550 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/exposure-snapshot/ods-domain-data`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `client-java/uds-client` (1 refs), `exposure-snapshot/snapshot-common` (13 refs), `exposure-snapshot/snapshot-sdk` (1 refs)

**Imported by:** `client-java/uds-client` (2 refs), `exposure-snapshot/idempotency-filter` (6 refs), `exposure-snapshot/snapshot-api` (12 refs), `exposure-snapshot/snapshot-filter-query-service` (3 refs)

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `CacheProvider` | interface | 3 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CacheProvider.java:5` |
| `RedisCacheProvider` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/RedisCacheProvider.java:20` |
| `RedisClientFactory` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/RedisClientFactory.java:9` |
| `RedisConfigProvider` | interface | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/RedisConfigProvider.java:5` |
| `CacheConstants` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/constants/CacheConstants.java:3` |
| `DomainManager` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/dao/DomainManager.java:35` |
| `DomainResult` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/DomainResult.java:3` |
| `Field` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/Field.java:5` |
| `DomainService` | class | 2 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/services/DomainService.java:20` |
| `CacheConfigHelper` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CacheConfigHelper.java:5` |
| `CacheConfigMap` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CacheConfigMap.java:7` |
| `CacheKeyGeneratorWithVersion` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CacheKeyGeneratorWithVersion.java:10` |
| `CacheNames` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CacheNames.java:3` |
| `PooledRedisConfigProvider` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/PooledRedisConfigProvider.java:9` |
| `RedissonCacheDecorator` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/RedissonCacheDecorator.java:9` |
| `DomainItem` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/DomainItem.java:5` |
| `DomainSchema` | class | 1 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/DomainSchema.java:6` |
| `CachingStrategy` | interface | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CachingStrategy.java:3` |
| `CoreCacheManager` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/CoreCacheManager.java:23` |
| `GuavaCacheAdapter` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/GuavaCacheAdapter.java:12` |
| `GuavaCoreCache` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/GuavaCoreCache.java:12` |
| `Helper` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/Helper.java:6` |
| `RedissonCache` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/cache/RedissonCache.java:20` |
| `DomainDataHelper` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/helper/DomainDataHelper.java:8` |
| `DomainCache` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/DomainCache.java:3` |
| `DomainCacheEntity` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/DomainCacheEntity.java:3` |
| `ModelOption` | enum | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/ModelOption.java:3` |
| `ValuesConfiguration` | class | 0 | `exposure-snapshot/ods-domain-data/src/main/java/com/rms/unifiedstore/model/ValuesConfiguration.java:5` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/exposure-snapshot/ods-domain-data` | 31 | 2,550 | structural only |
