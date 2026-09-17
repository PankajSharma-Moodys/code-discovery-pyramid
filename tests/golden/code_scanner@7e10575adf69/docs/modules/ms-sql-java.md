# `ms-sql-java`

4 tracked files, 146 lines. Part of `tree` at commit `<HEAD>`.

> **This module is not fully covered.** Scopes not completed: `root/ms-sql-java`. Facts about the files in those scopes are missing, not absent.

## Dependencies

**Imports:** nothing in this repository

**Imported by:** nothing in this repository

## Entry points

- DowngradeProcessor declares a process entry point in ms-sql-java/downgrade-processor; it is one of the repository's separately-startable units. — `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/DowngradeProcessor.java:32`
- winrm_script declares a process entry point in ms-sql-java/downgrade-processor; it is one of the repository's separately-startable units. — `ms-sql-java/downgrade-processor/scripts/winrm_script.py:449`

## Configuration

- Configuration key 'CORRELATION_ID' is read at 1 site(s) in ms-sql-java/downgrade-processor. — `ms-sql-java/downgrade-processor/scripts/winrm_script.py:13`
- Configuration key 'HOME' is read at 1 site(s) in ms-sql-java/downgrade-processor. — `ms-sql-java/downgrade-processor/Dockerfile:4`
- Configuration key 'USER' is read at 1 site(s) in ms-sql-java/downgrade-processor. — `ms-sql-java/downgrade-processor/Dockerfile:3`

## Side effects

- DowngradeProcessor and Program are separate deployable units that exchange data through shared storage (37 shared target(s), including ACCGRP, Address, BIDET, Bridge.rb_trty). No import connects them, so no dependency graph shows this edge; it is reachability over packaged code, not an observed runtime call. — `ms-sql-java/downgrade-processor/src/main/java/com/rms/unifiedstore/downgrade/DowngradeProcessor.java:32` `ms-sql-java/downgrade-processor/src/main/resources/rollback-scripts/Rollback_V21_to_V18.sql:8551` `ms-sql-java/downgrade-processor/src/main/resources/rollback-scripts/Rollback_V25_to_V25.sql:36600` `service-api/RMS.UnifiedStore.Service.Api/Program.cs:34`
- ms-sql-java/downgrade-processor reads from the database, across 4 site(s). — `ms-sql-java/downgrade-processor/scripts/winrm_script.py:110` `ms-sql-java/downgrade-processor/scripts/winrm_script.py:125` `ms-sql-java/downgrade-processor/scripts/winrm_script.py:162`

## Ownership

- The schema for 'dbo' is owned by ms-sql-java/downgrade-processor, service-api/RMS.UnifiedStore.Service.Api, defined across 21 migration(s). — `ms-sql-java/downgrade-processor/src/main/resources/rollback-scripts/Rollback_V23_to_V22.sql:683` `ms-sql-java/downgrade-processor/src/main/resources/rollback-scripts/Rollback_V25_to_V25.sql:2066` `service-api/RMS.UnifiedStore.Service.Api/Resources/RollbackScripts/Rollback_V23_to_V22.sql:683` `service-api/RMS.UnifiedStore.Service.Api/Resources/RollbackScripts/Rollback_V25_to_V25.sql:2066`

## Scopes

How the partitioner cut this module, and what each leaf was authorised to read.

| Scope | Files | LOC | Status |
|---|---|---|---|
| `root/ms-sql-java` | 4 | 146 | structural only |
