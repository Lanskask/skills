# Service tiebreakers

For each confusing pair, find the one axis that separates the services. Paraphrased from the source article.

## Messaging: who consumes, and can they come back

- **SQS**: one consumer per message, gone once processed; retries and a dead-letter queue.
- **SNS**: broadcast to many subscribers, no retention, so a down subscriber misses the message for good.
- **SNS to SQS fan-out**: one queue per consumer gives each a durable copy; a new consumer is a new queue, with no
  publisher change.
- **EventBridge**: routes on event content; the producer never learns who listens.
- **Kinesis Data Streams**: retains records (24 h up to a year); independent consumers replay at their own position.
  Replay, ordered reprocessing or several analytics consumers means Kinesis.
- **Amazon MQ**: only for an existing app that speaks AMQP, MQTT, STOMP or JMS and will not be rewritten.
- **IoT Core**: device fleets with per-device certificates.

## Load balancing and edge: which layer to act at

- **ALB**: reads HTTP (path, host, header routing, WAF, listener auth, WebSockets).
- **NLB**: does not read the request; any TCP/UDP, fast, keeps client IP, static IP per zone, no path routing.
- **Gateway Load Balancer**: inserts inspection appliances inline without terminating the connection.
- Static IP plus path routing plus WAF: NLB in front, ALB as its target.
- Static IP plus nearest healthy Region, or an apex domain with DNS hosted outside AWS: Global Accelerator.
- **CloudFront**: caches and fails over between origins inside the request (no DNS). Seven HTTP methods only; other
  methods or non-HTTP go to Global Accelerator. Its certificate must be in `us-east-1`.

## Storage: the protocol the application already speaks

- NFS: EFS. SMB with NTFS ACLs and Active Directory: FSx for Windows. Parallel HPC throughput, S3-linked: FSx for
  Lustre.
- On-premises app that cannot move: Storage Gateway (file to S3, volume as iSCSI, tape for existing backup software).
- Moving data in: DataSync for scheduled incremental transfer; Snow devices when the link would take months.
- Block volumes: no cross-Region replication (copy snapshots); no in-place encryption (snapshot, encrypted copy, new
  volume); Multi-Attach is io1/io2, one AZ, never shared storage across zones. Prefer gp3 over growing gp2 for IOPS.
- Instance store is erased when the instance stops; EBS outlives the instance.

## Databases: access pattern first, then compatibility

- MySQL/PostgreSQL needing HA with low ops: Aurora. SQL Server licence cost is the problem: Aurora PostgreSQL with
  Babelfish. MongoDB-compatible: DocumentDB.
- Key-value or document at any scale: DynamoDB (400 KB item limit, partition-key discipline).
- Caches: DAX is only in front of DynamoDB; ElastiCache is general and never a system of record; MemoryDB gives
  microsecond reads and durability.
- Multi-Region: one writer with fast recovery is Aurora Global Database; both Regions writing is DynamoDB global tables.
  Cross-Region read replica (minutes) and cross-Region backup copy (hours) are cheaper when the objective is loose.
- Blue/green deployments protect against an upgrade that succeeds but breaks the app: the old environment stays intact.

## Analytics: does a cluster have to exist

- **Athena**: SQL over S3, no cluster, billed per byte scanned; usually cheapest.
- **Redshift**: complex, sustained, concurrent queries; Concurrency Scaling for bursts.
- **OpenSearch**: log search and near-real-time dashboards over changing document shapes.
- **EMR**: when you need Hadoop or Spark themselves; primary and core nodes never on Spot, task nodes are where Spot
  belongs.
- **Glue**: serverless ETL. **AWS Batch**: long queued container jobs. Serverless variants of the engines remove
  capacity planning when load is unpredictable.

## Identity: who the person is

- Employees into AWS accounts: IAM Identity Center with permission sets.
- Customers of your app: Cognito (user pool authenticates; identity pool trades a token for temporary AWS credentials).
- External vendor: cross-account role with an external ID (prevents confused deputy), never an access key.
- On-premises directory: AD Connector is cheapest; MFA, trusts, Group Policy or schema extensions need AWS Managed
  Microsoft AD (Simple AD supports none).
- Separating teams inside one account: attribute-based access control with session tags.

## Security: what each service can see

- **WAF**: HTTP requests (injection, bots, geography, rate limits). **Shield Advanced**: volume (floods, response team,
  cost protection). **Network Firewall**: all traffic including egress and non-HTTP. **Firewall Manager**: enforces the
  others across accounts.
- **Inspector**: known vulnerabilities in instances, images, functions. **Macie**: sensitive data, S3 only. **Access
  Analyzer**: public or cross-account reachability, and least-privilege policy from CloudTrail activity. **Security
  Hub**: aggregated posture. **Detective**: investigate one finding.
- **SCP** prevents actions across accounts; **RCP** prevents outsiders reaching your resources; **Config** only detects.

## Migration and commitments

- Business case: Migration Evaluator (Migration Hub only tracks). Process and network discovery: the Discovery agent
  (agentless collector cannot see inside the guest, but is the only option when no software may be installed).
- Rehost servers: Application Migration Service. Database with minimal downtime: DMS with change data capture; new
  engine adds Schema Conversion Tool. Shut-down VM image: VM Import/Export. DR for on-premises servers: Elastic Disaster
  Recovery.
- Commitments: Compute Savings Plan spans instances, containers and functions; EC2 Instance Savings Plan locks family
  and Region for a deeper discount; databases, caches and warehouses use reserved instances or nodes; DynamoDB has its
  own reserved capacity. For guaranteed capacity use On-Demand Capacity Reservations spread across zones (a zonal
  reservation in one zone guarantees capacity in the zone that just failed).

## EC2 specifics

- **Placement groups**: cluster (one AZ, low latency, tightly coupled HPC); spread (separate hardware, max 7 per AZ, few
  critical instances); partition (rack-aware systems like HDFS, HBase, Cassandra); precision time (microsecond clock
  sync). Capacity error on a cluster group: stop and start all instances in it.
- **Families**: M general default; C compute; R/X memory; T burstable (throttles to baseline when credits run out).
  Graviton gives better price-performance if the workload can be recompiled. Right-size the size before the family.
  Memory is not a default metric; it needs the CloudWatch agent.
- **Shell access**: Session Manager records session content, no inbound port. Instance Connect gives a one-time key and
  logs only the key push in CloudTrail. Storing SSH keys in a secrets manager does not audit anything.
- **Source/destination check**: disable on NAT, proxy, router and firewall instances or traffic silently drops.
- **Images**: bake software, never licence keys, IPs or tokens. Image creation reboots by default. EC2 Image Builder
  makes image builds reproducible.
- **Instance metadata**: require IMDSv2 everywhere and enforce it with an SCP; it protects the credential, least
  privilege limits what the credential is worth.
