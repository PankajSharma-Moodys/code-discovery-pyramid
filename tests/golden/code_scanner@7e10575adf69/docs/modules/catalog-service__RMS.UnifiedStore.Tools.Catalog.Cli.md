# `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli`

39 tracked files, 4,484 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** `catalog-service/RMS.UnifiedStore.Service.Catalog.Common` (42 refs), `catalog-service/RMS.UnifiedStore.Service.Catalog.Engine` (1 refs), `core/RMS.UnifiedStore.Core` (19 refs)

**Imported by:** nothing in this repository

## Public types declared here

| Type | Kind | Used by | Declared at |
|---|---|---|---|
| `AbstractVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/AbstractVerbGroup.cs:8` |
| `BootstrapVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Bootstrap/BootstrapVerbGroup.cs:12` |
| `CatalogDatabaseOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Data/CatalogDatabaseOption.cs:6` |
| `CatalogInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Bootstrap/CatalogInvoker.cs:15` |
| `CatalogInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Migrate/Metadata/CatalogInvoker.cs:26` |
| `CatalogInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Migrate/Schema/CatalogInvoker.cs:27` |
| `CatalogOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Bootstrap/CatalogOption.cs:6` |
| `CatalogOptions` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Metadata/CatalogOptions.cs:6` |
| `CatalogOptions` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Schema/CatalogOptions.cs:6` |
| `CleanVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Clean/CleanVerbGroup.cs:11` |
| `CountersInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Monitor/CountersInvoker.cs:12` |
| `CountersOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Monitor/CountersOption.cs:6` |
| `DataInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Migrate/Data/DataInvoker.cs:19` |
| `DataVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Data/DataVerbGroup.cs:10` |
| `DatabaseVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Bootstrap/Database/DatabaseVerbGroup.cs:10` |
| `DatabaseVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Clean/Database/DatabaseVerbGroup.cs:10` |
| `IInvoker` | interface | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/IInvoker.cs:7` |
| `IOption` | interface | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/IOption.cs:3` |
| `IVerbGroup` | interface | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/IVerbGroup.cs:6` |
| `IntegrationTestDataInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Migrate/Data/IntegrationTestDataInvoker.cs:21` |
| `IntegrationTestDataOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Data/IntegrationTestDataOption.cs:7` |
| `IntegrationTestInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Clean/Database/IntegrationTestInvoker.cs:16` |
| `IntegrationTestOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Clean/Database/IntegrationTestOption.cs:7` |
| `MetadataVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Metadata/MetadataVerbGroup.cs:10` |
| `MigrateVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/MigrateVerbGroup.cs:13` |
| `MonitorVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Monitor/MonitorVerbGroup.cs:10` |
| `PostgreSqlInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Bootstrap/Database/PostgreSqlInvoker.cs:11` |
| `PostgreSqlInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Clean/Database/PostgreSqlInvoker.cs:14` |
| `PostgreSqlOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Bootstrap/Database/PostgreSqlOption.cs:7` |
| `PostgreSqlOption` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Clean/Database/PostgreSqlOption.cs:7` |
| `Program` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Program.cs:32` |
| `CatalogDatabaseInvoker` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Invoke/Migrate/Data/CatalogDatabaseInvoker.cs:25` |
| `RootVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/RootVerbGroup.cs:13` |
| `SchemaVerbGroup` | class | 0 | `catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli/Options/Migrate/Schema/SchemaVerbGroup.cs:10` |

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/catalog-service/RMS.UnifiedStore.Tools.Catalog.Cli` | 39 | 4,484 | structural only |
