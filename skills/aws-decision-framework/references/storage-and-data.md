# Storage and Data

Load this file when choosing or troubleshooting S3, EFS/FSx, data-transfer services, RDS/Aurora, DynamoDB and other
non-relational stores, analytics or streaming services.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

## S3: object storage, and the three-part permission model

### What it is

- Objects live in buckets, addressed by key. Object size: 0 up to 48.8 TiB (was 5 TB for years, still often quoted).
  Metadata key-value pairs behave like HTTP headers.
- Flat namespace: slashes in keys are not directories.
- Not a filesystem: no partial modify (append = rewrite whole object), no POSIX, no file locking, no atomic rename, no
  user/group permissions. Treating it as cheap NFS fails eventually.
- Buckets live outside your VPC: no security group, reachable from the internet unless policy says otherwise. Security
  is policy, not network isolation.
- Solves: durable, effectively unlimited, no capacity planning, very cheap per GB. Default home for data lakes, backups,
  static sites, logs, build artifacts.
- Durability vs availability are different promises. Durability: data loss effectively off the table, so no need to
  replicate to avoid loss. Availability: ordinary, occasional failed requests at high volume, so need retries and
  sometimes a second Region.
- Consistency: strongly read-after-write consistent for all operations (since Dec 2020, free, no setting). Delay loops,
  marker rows, side-channel markers for eventual consistency are obsolete; a design doc warning about it predates 2021.
- Hard decisions come from: storage classes (cost vs retrieval time), cross-account access (more pieces than expected),
  hidden cost characteristics.

### Storage classes

| Class                      | Rule                                                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Standard                   | Default; millisecond access, no retrieval fee, highest storage price                                                      |
| Standard-IA                | Cheaper storage + per-GB retrieval charge; for a known, scheduled drop-off ("rarely touched after 180 days")              |
| Intelligent-Tiering        | Unknown/changing/mixed access; automatic tiering, no retrieval fee                                                        |
| One Zone-IA                | Single copy in one AZ, about 20% cheaper than Standard-IA; data lost if the zone is destroyed; only for re-creatable data |
| Glacier Instant Retrieval  | Archive pricing, millisecond access                                                                                       |
| Glacier Flexible Retrieval | Expedited 1-5 min, standard 3-5 h, bulk 5-12 h                                                                            |
| Glacier Deep Archive       | Cheapest in AWS; 12-48 h retrieval                                                                                        |
| S3 Express One Zone        | Speed, not economy (see below)                                                                                            |

- Intelligent-Tiering details:
  - Three automatic tiers, all millisecond access: Frequent, then Infrequent after 30 days without access, then Archive
    Instant Access after 90.
  - Two optional tiers, Archive Access and Deep Archive Access: must be switched on deliberately and involve a restore
    step.
  - Objects under 128 KB are never transitioned; small per-object monitoring charge, so poor for huge numbers of tiny
    objects.
- One Zone-IA fits: derived thumbnails, transcoded renditions, secondary backup copy, intermediate analytics output.
  Requirement keyword: "re-creatable". Wrong for anything else regardless of price.
- S3 Express One Zone:
  - Single-digit-ms first-byte latency, up to roughly 10x faster than Standard; data in one AZ you choose (ideally the
    compute's AZ).
  - Storage costs considerably more per GB, request charges much lower; pays off for enormous numbers of small requests
    on a modest dataset (ML training loops, interactive analytics, media rendering).
  - Uses a directory bucket (different naming, session-based auth); you cannot switch an existing bucket to it.
  - Single-zone caveat as One Zone-IA: performance tier, not durability tier.
- Choose Deep Archive only when the requirement explicitly says retrieval speed does not matter; any time pressure makes
  it wrong regardless of price.
- Archived objects are not readable in place. Query engines do not thaw them; restore is a separate step with its own
  latency, and reads before restore completes fail.

### Lifecycle and replication subtleties

- Changing default bucket encryption is not retroactive; existing objects keep their encryption until copied. Re-encrypt
  millions of objects with batch operations, not a scripted loop.
- Ordinary replication copies only objects created after enabling; use batch replication for existing data. Versioning
  is a hard prerequisite on source and destination (most common replication mistake).
- Replication Time Control: 99.99% of objects within 15 minutes, publishes metrics to alarm on. Only replication option
  with an SLA; can be scoped to a prefix.
- Lifecycle rules transition and expire; they do not copy between buckets. Replication copies.
- Replication is a bucket feature; it does not apply to block-storage snapshots (AWS-managed storage, copied by a
  different mechanism).
- Writing to Standard then transitioning next day pays a day of Standard for nothing; write directly to the known
  destination class.

### Conditional writes, and the overwrite nobody notices

- Failure mode: two processes read, modify, write the same object; the second write wins silently, the first's work is
  lost, with no error or record.
- `If-None-Match: *` succeeds only if no object exists at the key: safe create, simple distributed lock.
- `If-Match` with an ETag succeeds only if the object is unchanged since read: optimistic concurrency. On rejection,
  retry against current state.
- ETag: MD5 of content for simple upload; for multipart it is computed differently and is not a content hash. Irrelevant
  for conditional writes (compared, not interpreted).
- Use whenever several writers share a key and last-write-wins is unacceptable. Versioning preserves the overwritten
  copy for recovery but neither prevents the overwrite nor tells the loser.

### The cost traps

- Incomplete multipart uploads: invisible in normal listing, billed indefinitely. A lifecycle rule to abort incomplete
  uploads after a few days is close to mandatory (commonly missed on bills). Many of them also signals something failing
  regularly.
- Managed key-service encryption adds a per-object-operation request charge. Bucket Keys cut it by up to 99%
  (bucket-level key cache, same encryption type). SSE with S3-managed keys removes the charge entirely. When the
  complaint is key-service request cost, answer is bucket keys, not switching encryption type.
- One object per tiny record: millions of sub-4 KB objects cost far more in requests than storage; put them in a
  database.
- CDN in front is cheaper per GB than serving from S3 directly and cuts requests reaching the bucket: two savings,
  decisive for large public downloads. Requester Pays is a billing arrangement for deliberate data-sharing, not a
  performance feature and not the answer to expensive public downloads.

### Performance

- Stop following eventual-consistency advice (see above): GET after successful PUT returns the new object; remove such
  scaffolding.
- Transfer Acceleration: uploads go to nearest edge then AWS backbone; fixes geographic distance for uploads into the
  bucket, not downloads to viewers (use a CDN for downloads).
- Multipart upload: mandatory above 5 GB, sensible above about 100 MB; parallel parts, retry a single failed part, cures
  intermittent upload failures on poor connections. Does nothing for geographic distance (resilience and latency are
  different problems).
- Random key prefixes are obsolete; S3 scales prefixes automatically and the technique never helped as folklore claims.
- Mountpoint for Amazon S3: file-API reads, always fetches the current object, no sync pipeline; for read-heavy access
  to large objects. For true POSIX semantics including writes, a Lustre file system linked to the bucket (heavier,
  complete).

### Multi-Region patterns

- Cross-Region replication plus a CDN origin group: automatic origin failover with no code change; triggers only on
  configured 4xx/5xx responses and only for GET and HEAD.
- Two-way replication plus a Multi-Region Access Point: one global endpoint routing to nearest bucket, for apps that
  read and write in several Regions. One-way replication with the second Region writing to its own bucket leaves
  datasets permanently divergent (invisible until compared).
- Multi-Region Access Points are one of few S3 features supporting private connectivity: on-premises can reach them over
  a dedicated connection, not the public internet.
- Write locally and let replication carry data to a central bucket: removes long-haul transfer from the critical path;
  usually better than accelerating the long write.

### The permission model

- A bucket is a Regional endpoint, not in your VPC: cannot go in a subnet, no security group. "Restrict to our network"
  is a policy problem: bucket policy condition on the source VPC endpoint.
- Three parts, not two:
  - Cross-account access needs both a bucket policy (owner account) and an identity policy (caller account).
    Same-account needs only one, which is why internal permissions break once another account is involved.
  - Customer-managed key on the bucket: third requirement, permission on the key (key policy or grant). Most commonly
    forgotten; symptom: caller can list objects but not read them.
  - Diagnostic: reads succeed but writes fail on an encrypted bucket = missing data-key generation permission (writing
    generates a data key; reading only decrypts).
- Listing acts on the bucket ARN; getting an object acts on the object ARN (bucket ARN plus `/*`). Granting only the
  object form silently breaks listing with an unclear error.
- Condition placement: on the caller's role it restricts that role; on the bucket policy it restricts everyone. To block
  anyone outside a named network or organization, the control must be on the bucket.
- Cross-account copy: pull from the destination account so it owns the resulting objects. Pushing from the source leaves
  the source owning objects in someone else's bucket. Modern alternative: bucket-owner-enforced ownership setting, which
  disables ACLs and assigns every new object to the bucket owner.
- Access points: created in the bucket owner's account, each with own policy, optionally restricted to a VPC; delegate
  via a bucket policy conditioned on the access point. Cannot be created in a consumer's account pointing at another's
  bucket; not route table targets (reached by name).
- Per-user prefixes: policy variable differs by identity type; IAM-user form for IAM users, principal-tag form for
  identity-center principals. IAM-user form does not resolve for federated identities.
- At scale use Access Grants: bucket policies have a size limit; Access Grants map identities (including groups
  federated from an external provider) to buckets, prefixes or objects without growing a policy.

### Protecting data

- Block Public Access with ignore-public-ACLs neutralizes every public ACL instantly at bucket level without rewriting
  objects; a script over a large bucket is too slow when the need is to stop exposure now. Presigned URLs keep working
  (different authentication).
- Object Lock compliance mode: WORM that not even the root user can shorten; survives credential compromise. Governance
  mode can be lifted by a privileged principal: wrong when the threat is a privileged attacker.
- Encryption in transit: bucket policy denying requests where the secure-transport condition is false. ACLs cannot
  express conditions.
- A bucket policy with an anonymous principal = a public bucket, whatever else the design says.
- A requirement naming an encryption type is read literally (e.g. S3-managed keys rules out all key-service options). If
  the key must be managed by the company and rotated on its schedule, only a customer-managed key qualifies.
- Encryption happens on write; nothing encrypts on read. Changing encryption always means rewriting the data.

### Logging and visibility

- Object-level activity needs CloudTrail data events; management events (the default) do not cover object operations, so
  object access is invisible until data events are enabled.
- Server access logging is best-effort and can drop records: unsuitable for compliance; the guaranteed record is
  CloudTrail data events.
- Storage Lens: account-wide dashboard across all Regions and buckets, including new ones (organization-level
  visibility). Storage Class Analysis: per bucket or prefix, only recommends Standard to Standard-IA.
- S3 Inventory: scheduled flat-file report of every object and metadata; the only sane way to audit/reconcile a bucket
  with tens of millions of objects (API listing does not finish usefully).
- No bucket-configuration events: event notifications fire only on object events (puts, deletes). A design waiting for a
  "bucket became public" event waits for something nonexistent; configuration drift is the configuration service's job.

### When not to reach for S3

- Application needs a filesystem and cannot change (locking, partial writes); no mounting tool makes S3 POSIX.
- On-premises system needs SMB or NFS access: copying into a bucket gives no share to mount; something must present the
  protocol.
- Endpoint must be private: static website hosting uses a public website endpoint and cannot be put behind a private
  endpoint. Private static content = CDN with origin access control, or an ordinary object read through a VPC endpoint.

## Shared file systems: EFS and FSx

- Real file system mounted by many servers at once: permissions, directories, partial writes; unmodified filesystem apps
  work.
- Solves: software that cannot use an object API (CMS, legacy analytics, home directories, build systems, anything that
  `open()`s a path); concurrent read-write from several machines without sync jobs.
- Cost: several times block storage per GB and far more than object storage; worth it for concurrent multi-writer access
  across AZs, waste otherwise (write-once output read by nothing else belongs in a bucket).
- Choose by operating system and protocol first: Linux/NFS, Windows/SMB, HPC each point to a different service.

### EFS

- Multi-AZ, POSIX, NFS shared file system. One mount target per AZ subnet; any NFSv4-compatible client (essentially
  every Linux distribution, nothing to install).
- NFS/POSIX: cannot express Windows ACLs; never the answer for a Windows file server.

### Performance, which is where the surprises live

- Throughput modes:
  - Elastic: current default and AWS recommendation; scales automatically, nothing provisioned, pay for data
    read/written; right for spiky or unpredictable workloads (most).
  - Provisioned: fixed throughput independent of stored size; for known requirements or high sustained average-to-peak
    ratio.
  - Bursting: throughput tied to stored size; baseline 50 KiBps per GiB in Standard class; credits accrue below baseline
    and are spent above; metadata operations spend credits too (small-file listing hurts).
- "Small file system cannot go fast" is true only under Bursting (no longer default). 100 GiB in Bursting: 5 MiBps
  baseline, bursts to 100 MiBps only while credits last; same file system on Elastic has no such ceiling. If a file
  system falls off a cliff, check mode first and watch the burst-credit balance metric (trending to zero = stall).
- Reads are metered at one third the rate of writes: 75 MiBps provisioned supports about 225 MiBps of reads; applies
  across modes.
- Performance modes: General Purpose = lowest per-operation latency, default, AWS recommends it for all file systems.
  Max I/O is previous-generation: higher aggregate ceiling for highly parallel workloads at higher per-op latency; not
  supported with Elastic throughput or on One Zone; encountered on existing systems, not chosen today; never fixes
  latency (makes it worse).
- Performance mode is fixed at creation (change = new file system and migrate). Throughput mode can change on a live
  file system, but after switching to Provisioned or changing the provisioned amount you cannot switch away or decrease
  for 24 hours.
- Tightly coupled HPC at scale: EFS is wrong regardless of tuning; use Lustre.

### Everything else worth knowing

- Cross-Region replication RPO about 15 minutes.
- Mountable on-premises over VPN or dedicated connection: share one live file system between data center and AWS with no
  sync job.
- No event notifications. Apps polling for new files are the symptom; refactor by moving the drop location to an object
  store, which emits events.
- Fixes the anti-pattern of copying static content onto every instance's block volume: one shared consistent copy, works
  across AZs (unlike a block volume).

### FSx

- FSx for Windows File Server: SMB, NTFS ACLs, Active Directory integration, Multi-AZ. Answer for any Windows/SMB
  workload.
- Throughput capacity and storage type changeable in place. Storage can only increase, never decrease, with about 6
  hours minimum between increases: size with headroom and automate growth. HDD to SSD is supported; reverse is not. No
  shrink after a spike.
- Watch the free-storage-capacity metric and drive automatic expansion from an event rule (standard capacity-alarm
  pattern).
- No native cross-Region replication; use a transfer service between two file systems. Bills on provisioned capacity, so
  an expensive backup target vs object storage (not close).
- FSx for Lustre: high-performance file system for compute-intensive work; links directly to an S3 bucket, presents
  objects as POSIX and writes results back. The answer for genuine POSIX over S3-resident data that cannot be rewritten.
- Lustre is mounted with the Lustre client, not NFS ("mount Lustre using NFS" is self-contradictory). Not a
  general-purpose NFS share, not a Windows home-directory solution, not supported on Fargate.

## Moving data in: gateways, sync and physical transfer

- The services are not interchangeable. Two attributes resolve nearly every choice:
  - Protocol of the other end: SMB, NFS, iSCSI, SFTP, tape library interface.
  - Direction and duration: one-time bulk, continuous sync, or permanent hybrid.

### Storage Gateway: speak the old protocol, store in the cloud

- Virtual appliance in your data center giving on-premises systems an AWS-backed target in a protocol they know; nothing
  on the client changes.
- File Gateway: SMB or NFS on-premises, data stored as objects in S3. It is an on-premises cache in front of S3, not a
  cloud file system. AWS consumers see objects, not an SMB share. If something in AWS needs an actual SMB share, not the
  answer.
- Volume Gateway: iSCSI block only; SMB/NFS apps will not work, no configuration changes that.
- Tape Gateway: virtual tape library for backup software that expects one (old backup product keeps working, tapes
  become objects). Only that backup software can read the virtual tapes; analytics or image-recognition services cannot
  parse them.

### DataSync: the bulk copier

- Managed, agent-based copy between on-premises and AWS or between AWS storage services; verification, scheduling,
  bandwidth throttling built in. Fits "move a lot of files, repeatedly, and tell me if anything was corrupted".
- Moves files, not database contents.
- For an on-premises source, run the agent on-premises; on EC2 the data crosses the link before the agent sees it,
  defeating the purpose.

### Transfer Family: a managed protocol front door

- Managed SFTP, FTPS and FTP endpoints landing files directly in S3 or EFS (replaces running your own SFTP fleet).
- A front door, not a replicator: does not sync two filesystems.
- Default public endpoint cannot be restricted by IP address or security group. If customers allow-listed an address or
  you need network controls, use the VPC-hosted endpoint type.
- An ALB is HTTP/HTTPS only and cannot front SFTP; a single stateful file-transfer server in an Auto Scaling group gives
  restarts, not scale.

### Snow devices: when shipping beats transmitting

- Physical hardware mailed by AWS; for large datasets over slow links a courier is faster (100 TB over a saturated 100
  Mbps link takes months).
- Corollary: with a fast link already present, shipping is slower (days each direction vs hours). Smallest device holds
  single-digit TB, nowhere near archive-scale migration.
- Snowcone: small, rugged, a couple of handfuls of TB, battery-operable. Discontinued 12 Nov 2024, support for existing
  devices ended a year later (history; DataSync is what AWS points to). Older material still shows it for constrained
  edge sites.
- Snowball Edge, two variants often confused:
  - Storage Optimized: max capacity, for bulk data migration.
  - Compute Optimized: fewer TB, more vCPUs, memory, optional GPU; runs EC2 and Lambda on the device at the edge, often
    disconnected. Answer to "process data where generated, ship only results".
- Snowmobile: shipping container for exabyte-scale data-center evacuation; retired (removed from AWS site during 2024).
  Survives in study material as the answer to "move an exabyte".
- All: data encrypted with KMS keys you control, AWS never holds the key (a lost device is not a breach). Devices can be
  clustered for durability and higher aggregate capacity.
- A device moves a one-time bulk load only; for existing data plus ongoing changes, pair a device (backlog) with a sync
  service (delta).

### Cross-cutting judgments

- If the systems speak exactly one protocol, that rules out every design assuming another (FTP-only device rules out
  NFS-based answers and file-sync agents, however good in the abstract).
- Writing to Standard then transitioning next day pays a day of Standard for nothing; write to the target class
  directly.
- AWS Backup covers AWS resources and specific supported on-premises arrangements, not an arbitrary file server with
  bespoke directory filters. A hand-rolled copy script is not the alternative (unmaintained pipeline).

## Relational databases: RDS, Aurora and connection pooling

- RDS: MySQL, PostgreSQL, SQL Server, Oracle, MariaDB as a managed service (provisioning, backups, patching, failover,
  replication). Aurora: AWS's own engine, wire-compatible with MySQL and PostgreSQL, distributed storage layer keeping
  six copies across three AZs.
- Trade of managed: you get a database, not a server; less control.
- Not included in "managed":
  - Engine feature parity is incomplete (an extension/plugin/server-level feature may be unavailable); decide before
    migrating.
  - You still own performance: RDS sits on block storage and inherits its characteristics; starved of IOPS behaves like
    self-managed.
- Parameter group = engine settings; option group = optional engine features. Defaults are read-only: you must create
  your own and reassociate, sometimes with a reboot. Create your own at the start (otherwise found during an incident).
- Cost win: stop non-production databases on a schedule (24h dev DB for an 8h team is three-quarters waste).
- Recurring decision: availability topology (what fails over, how fast, how much data lost, can the standby serve
  reads).

### Multi-AZ, replicas and what each actually gives you

- Classic Multi-AZ: synchronous standby in another AZ, passive failover target, serves no reads. Proposals to offload
  reads to it are wrong.
- Exception: Multi-AZ DB Cluster deployment has readable standbys (two deployment types, similar names, different
  capabilities).
- Failover is a DNS change: same endpoint name, new address. Clients caching DNS aggressively (JVM default is the
  classic offender) keep using the old address; failover looks like minutes instead of seconds. Check client DNS caching
  before blaming the platform.
- Read replicas: asynchronous, manual promotion; scale reads well; satisfy neither tight RPO nor RTO alone (lag
  seconds-to-minutes, promotion is an operator action). Cross-Region replicas: same caveats plus distance; for MySQL
  strictly read-only (cannot forward writes).
- No automated cross-Region failover promoting a standard replica; promotion is an API call or script (typically
  CloudWatch alarm invoking a function). A design claiming automatic cross-Region promotion describes a nonexistent
  feature.
- Read replicas do not scale writes; if writes are the bottleneck more read capacity changes nothing.
- Aurora Global Database: storage-layer cross-Region replication, RPO about 1 second, promotion under a minute. For
  genuinely tight objectives; costs considerably more, so it loses a comparison whose priority is lowest cost with
  generous objectives (over-delivering on recovery is still over-delivering).
- Headless secondary: a global-database secondary cluster with no reader instances; storage replication continues (RPO
  holds), no idle compute paid until promotion.
- Objective tightness drives design: RTO under 10 minutes with a large database forces continuous replication; at 20
  minutes a scripted replica promotion becomes viable and much cheaper.

### Aurora specifics

- Reader endpoint load-balances across replicas, not for writes (read-write workload on it fails mysteriously). Writer
  endpoint follows failover automatically.
- Aurora Serverless: automatic capacity for genuinely variable load; for explicitly consistent load, reservations win on
  cost. First generation lacked cross-Region capabilities (rules it out of DR designs needing them).
- Serverless v1: retired 31 Mar 2025, remaining clusters force-upgraded (matters for reading older designs only). Scaled
  by swapping the whole instance for a larger one (tens of seconds, needs a quiet moment); can pause to zero when idle
  (good for dev, unacceptable for user-facing).
- Serverless v2: scales in place in increments of half an Aurora Capacity Unit, in a second or less, no connection drop;
  participates in Global Database; supports read replicas; can share a cluster with provisioned instances (provisioned
  writer plus serverless readers absorbing unpredictable reporting load). Has a floor you pay continuously; cannot pause
  to zero.
- Pick: unpredictable production traffic that must stay responsive = v2; dev database that should cost nothing overnight
  = v1; steady production at known size = provisioned (serverless carries a per-unit premium that pays off only with
  genuinely varying capacity).
- Blue/green deployments: full staging copy kept in sync by replication; apply major version upgrade or schema change
  there while production runs. Switchover is a single operation, typically under a minute, blocked if replication lags.
  Protects against the upgrade succeeding but the application being incompatible (old environment remains intact).
- Multi-writer Aurora: narrow set of conflict-free workloads; not general write scaling.
- Aurora replicates the entire storage volume, not individual tables; "add a Region to a table" is DynamoDB vocabulary
  on the wrong engine.
- Babelfish for Aurora PostgreSQL: understands SQL Server wire protocol and T-SQL, so a SQL Server app connects to
  PostgreSQL with little or no data-access-layer change. Shortcut for escaping commercial licensing without a rewrite.
- Moving SQL Server to RDS for SQL Server keeps the license cost (changes operator, not licensing); only changing engine
  removes the license.

### Connections

- Connection pool exhausts long before CPU, especially with serverless compute in front. Raising the connection limit
  needs a reboot and only postpones the problem.
- RDS Proxy: pools and reuses connections (structural fix). Needs credentials in a secrets manager (cannot read
  parameter store); fronts managed databases only, never on-premises.
- Cross-account pattern: RDS Proxy behind a Network Load Balancer published as a private endpoint service: proxy pools,
  endpoint gives private one-way access, no peering needed.
- Data API: avoids the problem instead of managing it. Available for Aurora Serverless and Aurora PostgreSQL provisioned
  clusters; SQL sent as API call over secure HTTP with IAM authentication and Secrets Manager credentials; no persistent
  connection. Removes pool exhaustion, the need for the caller to be in the VPC, and driver/credential handling in the
  function. Good for Lambda or browser-facing services querying occasionally; wrong for sustained high-throughput
  (per-request overhead exceeds a pooled connection).
- RDS Proxy vs Data API for serverless compute: both valid; tiebreaker is whether the caller needs to be in the VPC at
  all.

### Backups and migration

- Automated backups: once a day, max 35-day retention; cannot be set to a 6-hour cadence; a schedule the platform or
  hardware cannot deliver is not a plan (e.g. full snapshot of 10 TB every 5 minutes). For RPO of minutes use a replica;
  scheduled backups are not the mechanism, and neither is the managed backup service (it schedules the same snapshots).
- The lifecycle manager for block-storage snapshots does not support RDS.
- An automated snapshot must be copied to a manual snapshot before sharing with another account.
- Blue/green for managed databases: synchronized staging copy of the whole database; upgrade or change schema there;
  switchover typically under a minute with writes blocked only during switch. Modern answer for a major version upgrade
  with no outage allowed.
- Database Migration Service moves data between engines:
  - Full load without change data capture: copy frozen at the moment it finished.
  - CDC alone without full load: never brings pre-existing rows.
  - CDC records data changes only; cannot satisfy a requirement to capture all activity including reads and admin
    actions (audit, not replication).
  - A migration tool, not a DR posture; running it forever is not a recovery plan.
- Schema Conversion Tool: converts schema and procedural code; only needed when the engine changes (unnecessary for
  homogeneous). Oracle with stored procedures to PostgreSQL: conversion tool plus migration service is the standard
  pairing.
- Converting a relational transactional DB to a graph or key-value engine is a re-platform, not a migration, and loses
  any minimize-change requirement. A query engine over object storage is not a transactional endpoint: it answers
  analytical questions; single-row low-latency reads/writes need a database.
- Moving from provisioned-IOPS to general-purpose storage reduces I/O capability: a cost measure, never a performance
  fix.

## DynamoDB and the non-relational family

- Managed key-value and document database, single-digit-ms latency at essentially any scale; no servers, no patching, no
  SQL.
- Trade: gives up query flexibility for predictable performance and horizontal scale (relational scales writes poorly
  and needs capacity planning). Design the table around access patterns up front.
- Primary key = partition key, or partition key plus sort key; it distributes data and retrieves efficiently. Query = ms
  at any scale; scan = reads every item and you pay. Secondary indexes provide extra access patterns and are part of
  schema design. A table designed without knowing the queries will be rebuilt.
- Honest trade-off: proprietary, no interface-compatible open-source equivalent; leaving is a data-layer rewrite. Usual
  comparison: Cassandra, which AWS offers as managed wide-column (Keyspaces) for teams wanting compatibility.
- A local version runs on a laptop (see DynamoDB Local below).

### The constraints that shape designs

- Item size max 400 KB. Larger: store the blob in an object store, keep the key in the item. Base64 inflates size by
  about a third (worse).
- Capacity modes: on-demand charges per request and costs several times more than well-sized provisioned for large,
  steady, predictable load. Provisioned with auto scaling for predictable load; on-demand for spiky/unknown. DynamoDB's
  prepayment construct is reserved capacity (different from compute reservations).
- Read and write capacity are separate; a failing write path is not fixed by read capacity.
- Hot partition: data spread by hashing the partition key; each partition has a hard ceiling of about 3,000 read units
  and 1,000 write units per second regardless of table provisioning. Example: table provisioned at 40,000 write units
  with all traffic on one partition key gets 1,000 and throttles. Most common reason a table underperforms while
  table-level metrics look healthy.
- Causes: low-cardinality or time-biased partition key (status field, country code, one huge tenant, today's date).
  Fixes are design-time:
  - Pick a high-cardinality, evenly accessed key.
  - Write-shard a skewed key: append a bounded random suffix, read across shards.
  - Move the time component from the partition key to the sort key.
- Adaptive capacity: continuously reallocates throughput to busier partitions and eventually splits a persistently hot
  one; free; effective for mild gradual skew. Cannot rescue a key with four possible values or react fast to a sudden
  spike on one key. A cushion, not a design. Throttling on one key despite ample capacity: fix the partition key, not
  capacity nor adaptive capacity.
- Backups:
  - Point-in-time recovery: continuous log, restore to any second in the last 35 days; for accidental delete, bad
    deployment, RPO in minutes. Must be enabled before the incident (enabling after recovers nothing).
  - On-demand backups: explicit full snapshots kept until deleted; for retention obligations of years.
  - Both restore to a new table, not over the existing one (recovery plan needs a cutover step).
- DAX: read-through cache, microsecond reads; no help for write-heavy tables; highly available deployment needs at least
  3 nodes (1 or 2 nodes fail an availability requirement).
- DynamoDB Streams: ordered record of every change; turns the DB into an event source (replicate, derived view, trigger
  a function per write, audit log); answers "react when data changes" instead of polling.
- Global tables: multi-Region active-active, built on streams; solve geographic availability, not single-Region
  throughput. An existing table can be converted to a global table (no new table and copy). Where global tables exist, a
  general-purpose migration service for cross-Region table replication is reaching past the purpose-built answer.
- TTL: per-item expiry timestamp, automatic deletion at no charge (session tables, transient records).
- DynamoDB Local: downloadable (laptop or container), same API; develop and test without cloud account, latency or bill.
  Answers "local dev would be painful" objection. Development aid, not production; does not reproduce partition
  behaviour at scale.
- Finding unused tables: consumed-capacity metrics over a long window (throttle metrics show shortfalls, not idleness).
  Cost reduction: Standard-Infrequent Access table class and on-demand mode (nothing per request while idle). Dropping
  provisioned capacity to its floor cuts cost but fails any requirement to preserve current performance capability.

### Choosing among the non-relational proposals

- Vocabulary selects the service: key-value = DynamoDB; document = DocumentDB; graph = Neptune; wide-column = Keyspaces;
  time series = Timestream. "Key-value" and "document" name different services.
- ElastiCache is a cache, not a primary datastore; fails any requirement that data persist for later processing.
  Memcached: no persistence, no failover, no cross-Region; needing reliability, durability or replication rules it out
  in favor of Redis.
- MemoryDB: Redis-compatible and durable (writes committed to a distributed transaction log across AZs); primary
  database with in-memory latency. Fits microsecond reads, single-digit-ms writes, no separate database of record.
- DocumentDB: provisioned by instance class; no serverless capacity mode. Moving a document workload to relational means
  rewriting the data access layer (not low-effort).
- A database and a cache running continuously between short bursts is idle infrastructure paid hourly: justify always-on
  capacity or use something that scales to nothing.

### Permissions

- Per-item fine-grained access control lives in IAM conditions; there is no resource-based policy on a DynamoDB table
  (unlike a bucket or queue). Permission boundaries cap but cannot express attribute-level filtering; organization-level
  policies restrict rather than grant.
- A fine-grained policy must cover the table's secondary indexes as well as the table; table-only access gives denied
  index queries that look like an app bug.

## Analytics: querying data where it lives

- Data stays in object storage in its own format; compute comes to it.
- Two questions choose the service: tolerable latency (seconds, minutes, hours)? Must a cluster exist when nobody is
  querying?

### The core selections

- Athena: SQL directly on S3, no cluster, billed per data scanned. Default for ad-hoc analysis; almost always wins cost
  against cluster engines (competitor still runs servers).
- Athena cost strategy is reducing scanned data: partition (query on one day reads one day), columnar format (3 columns
  read = 3 columns), compress. Consolidating files or a new bucket per day are workarounds for what partitioning solves.
  Athena cannot read archived objects without restoring them first.
- Federated query: same SQL over sources outside object storage (relational, key-value, on-premises) via connectors;
  join across without centralizing via a pipeline.
- Redshift: data warehouse for sustained complex analytical queries over structured data. Redshift Spectrum queries S3
  from a Redshift cluster, so it keeps the cluster and never wins a pure cost comparison against Athena (nor does any
  arrangement preserving the cluster).
- Redshift resizing: classic resize makes the cluster read-only for hours; elastic resize takes minutes (use elastic if
  the warehouse must serve throughout). Concurrency Scaling adds transient capacity when queries queue, then removes it
  ("Monday morning rush").
- Redshift node type decides cost: RA3 separates compute from storage (hot data on local SSD, rest in managed storage
  billed separately, scales on its own). Older dense-compute/dense-storage types tie them (growing storage means buying
  unneeded compute). For data that grows while query load stays flat, RA3 is the structural answer, not resizing. RA3
  also enables data sharing: one cluster reads another's data live without copying (reporting team access without
  duplicating or competing for compute).
- EMR: Hadoop, Spark etc. when you need the frameworks. Primary and core nodes hold cluster state and HDFS data, so no
  interruptible capacity; Spot belongs on task nodes. Cluster left running all day for a few hours of work wastes the
  rest; transient clusters (start, run, terminate) are the cost-aware pattern.
- Glue: serverless ETL plus a data catalog (central metadata store so services agree on tables). Crawlers infer schema;
  do not move data; Glue is not a DB replication tool. DataBrew: visual cleaning/normalizing without code, for people
  who understand the data but do not write Spark.
- OpenSearch: search and log-analytics engine you feed and operate. For searching across existing repositories with
  managed connectors and least effort, a dedicated enterprise search service fits better than building an index.
- QuickSight: BI and visualization; over a relational database it is not a near-real-time mechanism.
- Lake Formation: above the catalog; fine-grained data-lake permissions (database, table, column, row, cell level) with
  tag-based access control. Bucket policies and access points are the coarse alternative and cannot express "this team
  sees these columns".

### Streaming

- Kinesis Data Streams: retains data, multiple independent consumers on the same records, replay. Choose when more than
  one application needs the same stream, or ordering and replay matter.
- Data Firehose (Amazon Data Firehose): delivery stream that buffers and writes to a destination; no replay, no multiple
  consumers. Buffering interval means not real time (the phrase rules it out). Native destinations include search
  services and third-party endpoints: usual intermediary when logs must reach an external system.
- Dynamic partitioning is a Firehose feature, not Data Streams. Reducing shard count worsens a throughput problem. The
  producer library is a producer concern; it does nothing about a consumer-side error.
- Amazon MSK: for workloads already on Kafka; swapping Kafka for another streaming service means rewriting the messaging
  layer (loses low-effort requirements). Express brokers: higher throughput and faster recovery than standard brokers.
  Rack awareness: consumers read from a replica in their own AZ (latency and cross-zone cost).
- Amazon Managed Service for Apache Flink: computes over streams in flight (windowed aggregations, joins between
  streams, anomaly detection, enrichment against a reference table) with managed state and exactly-once processing. The
  other streaming services only transport. A Lambda reading a stream is stateless, sees one batch at a time ("average
  over last five minutes per device", "alert if A not followed by B within 30 seconds" would be built from scratch). Use
  for continuous aggregation, sessionization, pattern detection. Older name Kinesis Data Analytics = same service.
- Amazon Kinesis Video Streams: time-encoded binary media from cameras and sensors; ingests from thousands of devices,
  indexes fragments by time, stores durably, gives playback and frame-level access to analytics/ML via own APIs. Fits
  video from edge devices, time-indexed playback, computer vision over a camera fleet. General-purpose record streams do
  not work (record size limits and consumer model wrong for media).
- AWS Data Exchange: marketplace, not a pipeline. Find, subscribe to and auto-receive third-party datasets (financial,
  demographic, weather, healthcare) into S3 or queryable in place, with entitlements and revisions handled. Also lets a
  data seller publish and license datasets. Replaces scraping a vendor FTP site or re-signing contracts on format
  changes. Use for externally sourced reference data kept current with no ingestion pipeline to maintain.

### Judgments that recur

- A requirement to retain a copy of all input data forbids deleting the source after processing; lifecycle it to
  archival storage instead.
- Periodic exports to object storage leave subscribers with stale data and you owning a pipeline; a batch export fails a
  "most recent" requirement.
- A relational database is not a data warehouse (transactional, many small reads/writes, not scanning a billion rows).
- S3 Select queries a single object, not a dataset; closed to new customers in July 2024 (only existing-user accounts).
  Athena is where this work goes. Only avoids transferring a whole file to get part of one; not a query engine.
- Prefer the purpose-built service over the general-purpose one when both work. Training a custom model to read
  documents or recognize images loses on time to market against a managed service that already does it.
- Older orchestration: Data Pipeline was the original managed data-movement/scheduling service (legacy material still
  references it). New work goes to the serverless ETL service (Glue) and workflow orchestration; recognize the old name
  in inherited architectures but do not use it for new builds.
