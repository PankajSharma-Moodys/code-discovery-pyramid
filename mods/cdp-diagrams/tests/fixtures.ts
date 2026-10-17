// Synthetic diagrams with the same shapes and syntax as answers Claude
// writes (|label| and "-- label -->" edges, <br/> labels, db nodes, dashed
// inferred edges, self-loops, [*] states, composite states, notes). Every
// name and citation here is invented.

export const FIXTURES: Record<string, string> = {
  request_chain: `flowchart TD
  A["POST /v2/orders/{id}/items<br/>OrderResource#addItem"] -->|OrderResource.java:120| B["OrderMapper.toItem"]
  B -->|OrderResource.java:131-133| C["ItemService.create"]
  C -->|ItemService.java:44| D["ItemRepository.save"]
  D -->|"@Entity @Table<br/>ItemEntity.java:9"| E[("order_item table")]
  C -.->|"toOutput (inferred return path)<br/>OrderResource.java:140"| F["ItemOutput response"]
  E -.->|"findDue (worker, not traced)"| G["DueItemJob"]
  G -->|ItemEntity.java:9| H[("order_item table")]
  E -.->|"existing key: return early, ItemService.java:61-62"| I["return existing item"]`,

  request_chain_quoted: `flowchart TD
  A["POST /v2/orders/{id}/items<br/>OrderResource.java:98"] --> B["OrderResource#addItem<br/>OrderResource.java:120"]
  B -->|"toItem<br/>OrderResource.java:131"| C["Item"]
  C -->|"create<br/>ItemService.java:40"| D["ItemService.create"]
  D --> E[("order_item")]`,

  job_states: `stateDiagram-v2
    [*] --> QUEUED: initial (JobStatus.scala:5)
    QUEUED --> PENDING: moveToPending (JobService.scala:300)
    QUEUED --> CANCEL_REQUESTED: setCancelRequested (JobDao.scala:80)
    PENDING --> RUNNING: running task (job_state.sql:9)
    RUNNING --> DONE: total = succeeded (job_state.sql:10)
    PENDING --> DONE: total = succeeded (job_state.sql:10)
    RUNNING --> FAILED: failed task (job_state.sql:6)
    PENDING --> FAILED: failed task (job_state.sql:6)
    RUNNING --> CANCEL_REQUESTED: cancel (JobRepository.scala:211)
    CANCEL_REQUESTED --> CANCELLING: cancelling task (job_state.sql:7)
    CANCELLING --> CANCELLED: cancelled task (job_state.sql:8)
    CANCEL_REQUESTED --> CANCELLED: cancelled task (job_state.sql:8)
    DONE --> [*]
    FAILED --> [*]
    CANCELLED --> [*]`,

  job_states_gated: `stateDiagram-v2
    [*] --> QUEUED: create (core JobService.scala:57-62)
    [*] --> PENDING: create, gate open (core JobService.scala:61)
    QUEUED --> PENDING: release (JobService.scala:300)
    PENDING --> RUNNING: first task starts (job_state.sql:9)
    RUNNING --> DONE: all tasks ok (job_state.sql:10)
    RUNNING --> FAILED: a task failed (job_state.sql:6)
    DONE --> [*]
    FAILED --> [*]`,

  event_fanout: `flowchart TD
  A["JobDelegate.triggerStatusChangeEvent<br/>JobDelegate.scala:33-42"] -->|eventBus.post| B[Guava EventBus]
  A2["Worker JobService<br/>JobService.scala:131,198,219"] -->|eventBus.post| B
  A3["API JobService.cancelJob<br/>JobService.scala:216"] -.->|post, not verified| B
  B -->|"@Subscribe, registered at AppModule.scala:34"| C["JobSubscriber.onStatusChange<br/>JobSubscriber.scala:30"]
  C -->|"reload Job if JobBase, JobSubscriber.scala:39-45"| C
  C -->|"dispatcher.dispatch, JobSubscriber.scala:63"| D["EventDispatcher.dispatch<br/>EventDispatcher.scala:35-42"]
  D -->|"Future per listener, EventDispatcher.scala:37"| L1["LogPublisher.onStateChange<br/>LogPublisher.scala:34"]
  D -->|"Future per listener, EventDispatcher.scala:37"| L2["SocketPublisher.onStateChange<br/>SocketPublisher.scala:24"]
  L1 -->|"logger.info JSON, LogPublisher.scala:56"| O1[Log file]
  L2 -->|"HTTP POST, SocketPublisher.scala:39"| O2[Event server / UI]`,

  event_fanout_stadium: `flowchart TD
  A["JobDelegate.triggerStatusChangeEvent"] -->|"JobDelegate.scala:36-42 eventBus.post"| B(["Guava EventBus"])
  C["worker JobService cancel/fail/pending"] -->|"JobService.scala:131,198 eventBus.post"| B
  D["API JobService.cancelJob"] -.->|"JobService.scala:216 constructs event; bus post not verified"| B
  B -->|"AppModule.scala:34 register"| E["JobSubscriber.onStatusChange"]
  E -->|"JobSubscriber.scala:63"| F["EventDispatcher.dispatch"]`,

  create_db: `flowchart TD
  A["POST /v4/{tenantId}/Store<br/>StoreController.CreateStoreAsync"] -->|"v4/StoreController.cs:79"| B["CreateStoreHandler<br/>(scopeId overload)"]
  B -->|"Handler.cs:108 QueryCatalogAsync"| C["ICatalogService"]
  B -->|"Handler.cs:160 AcquireLock"| D["Redis lock"]
  B -->|"Handler.cs:236 AddStoreAsync"| E["StoreRepository.AddStoreAsync<br/>StoreRepository.cs:520"]
  E -->|"StoreRepository.cs:541-545"| F["DbContext.Stores.Add + SaveChanges"]
  F -.->|"inferred: EF convention, no ToTable found"| H[("Stores table<br/>State=Creating")]
  B -->|"Handler.cs:267"| J["CreateDatabaseJobAsync"]
  J -.->|"Handler.cs:400,428 (not traced further)"| C
  J -.->|"inferred"| H`,

  create_db_decls: `flowchart TD
  C["StoreController.CreateStoreAsync v4/v1<br/>v4/StoreController.cs:59"]
  H1["Handler overload (groups / scopeId)<br/>CreateStoreHandler.cs:68, :96"]
  H2["Private CreateStoreAsync<br/>Handler.cs:120"]
  R["Redis idempotency lock<br/>Handler.cs:160"]
  T[("table Stores<br/>DbContext.cs:486; Initial.cs:40")]
  X["DeleteStoreAsync rollback on failure<br/>Handler.cs:317"]
  C -- "v4/StoreController.cs:79" --> H1
  H1 -- "Handler.cs:82 / :116" --> H2
  H2 -- "Handler.cs:160" --> R
  H2 -- "Handler.cs:236" --> T
  H2 -. "on exception, Handler.cs:317" .-> X
  X -. "inferred: deletes the Stores row" .-> T`,

  store_states: `stateDiagram-v2
    [*] --> Creating: CreateStore/ImportStore (CreateStoreHandler.cs:152, ImportStoreHandler.cs:127)
    [*] --> Importing: RestoreBackup (RestoreBackupHandler.cs:285)
    [*] --> Ready: Register (RegisterStoreHandler.cs:139)
    Creating --> Ready: (CreateStoreHandler.cs:304)
    Importing --> Ready: inferred, not traced
    Ready --> Moving: (MoveStoreHandler.Pre.cs:53)
    Moving --> Ready: success (MoveStoreHandler.Post.cs:67)
    Moving --> Ready: rollback (MoveStoreHandler.Rollback.cs:160)
    Ready --> Deleting: no assignment found`,

  store_states_short: `stateDiagram-v2
    [*] --> Creating: CreateStoreHandler.cs:246 / CloneStoreHandler.cs:152
    [*] --> Importing: ImportStoreHandler.cs:220 / RestoreBackupHandler.cs:285
    Creating --> Ready: CreateStoreHandler.cs:480
    Importing --> Ready: ImportStoreHandler.cs:301
    Ready --> Deleting: DeleteStoreHandler.cs:90
    Deleting --> [*]: DeleteStoreHandler.cs:133`,

  instance_states: `stateDiagram-v2
    [*] --> Provisioning: SlotPool.allocate SlotPool.kt:88-93
    Provisioning --> Warm_pool: ProvisionTask ok :412-415
    Provisioning --> Broken: ProvisionTask error :420-424
    state Warm_pool {
        [*] --> Idle
        Idle --> Busy: lease() :57-60, :233
        Busy --> Idle: release() :71, :240
    }
    Warm_pool --> Retiring: Reaper.markStale :510-512
    Warm_pool --> Retiring: Reaper.rotate :530-533
    Broken --> [*]: Reaper.sweep :601 (result not read)
    Retiring --> [*]: Reaper.sweep :607 (result not read)`,

  instance_states_note: `stateDiagram-v2
    [*] --> Provisioning: slot row written (writer not traced)
    Provisioning --> Busy: ProvisionTask marks ready (SlotPool.kt:412, 470)
    Busy --> Idle: release (SlotPool.kt:71)
    Idle --> Busy: lease (SlotPool.kt:57)
    Provisioning --> Broken: error (SlotPool.kt:420)
    Busy --> Retiring: stale (Reaper.kt:510)
    Broken --> [*]
    Retiring --> [*]
    note right of Broken: Broken and Retiring slots are never leased (SlotPool.kt:45-46)`,

  left_right: `flowchart LR
  A[Client] -->|api.ts:12| B{Router}
  B -->|router.ts:40| C[Orders]
  B -.->|router.ts:52, flag off| D[(Legacy DB)]
  C --- E((Cache))`,
}
