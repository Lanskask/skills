# Limits that decide designs

Figures as reported by the source article (Nov 2026). Unverified; confirm in AWS documentation before relying on one.

## Ceilings that end a design

| Limit                         | Value                                                  | Usual way out                        |
| ----------------------------- | ------------------------------------------------------ | ------------------------------------ |
| Lambda duration (sync)        | 15 minutes (up to 90 min async on Lambda Managed Inst) | Fargate task with the same container |
| Lambda memory                 | 10,240 MB                                              | Rarely the limit; duration is        |
| Lambda payload                | 6 MB sync, 1 MB async                                  | Put the object in S3, pass the key   |
| API Gateway payload           | 10 MB                                                  | Same                                 |
| DynamoDB item                 | 400 KB (base64 adds about one third)                   | Same                                 |
| Lambda package                | 50 MB zip, 250 MB unzipped, 10 GB container image      | Layers are zip-only                  |
| S3 object / single PUT        | 48.8 TiB / 5 GB                                        | Multipart (up to 10,000 parts)       |
| S3 incomplete multipart parts | billed, invisible in listings                          | Lifecycle rule to abort them         |

## Failover and recovery ladders

- Failover: CloudFront origin group and Global Accelerator decide in the request (seconds). RDS Proxy cuts database
  failover by about two thirds. DNS can never beat TTL plus health-check interval plus resolver caching.
- Recovery point: Aurora Global Database about 1 s (recovery about 1 min planned; design for several minutes unplanned),
  cross-Region read replica minutes, cross-Region backup copy hours.
- S3 Replication Time Control: 99.99% of objects within 15 minutes. Ordinary replication promises nothing.
- Archive retrieval: Glacier Instant in milliseconds; Flexible expedited 1-5 min, standard 3-5 h, bulk 5-12 h; Deep
  Archive 12 h standard, 48 h bulk. Nothing thaws transparently; queries fail until restored.
- Backups: RDS automated backups daily, 35-day maximum, copy to a manual snapshot before sharing. AWS Backup cold
  storage has a 90-day minimum. A stopped RDS instance restarts itself after 7 days.

## Throughput and scale

- SQS FIFO: about 300 TPS per API action (about 3,000 msg/s batched) by default; high throughput mode needs many message
  group IDs. Standard queues are effectively unlimited.
- Kinesis shard: 1 MB/s or 1,000 records/s in; 2 MB/s and 5 reads/s out shared by standard consumers (use enhanced
  fan-out for a dedicated 2 MB/s each). Firehose buffering can be 0-900 s, so near-real-time is possible.
- EFS reads count at one third of writes. FSx for Windows storage only grows. Intelligent-Tiering ignores objects under
  128 KB.
- Network Firewall: 100 Gbps per AZ, not adjustable. API Gateway account-level throttle about 10,000 req/s with 5,000
  burst, shared by every API in the Region.

## Topology

- Spread placement group: 7 instances per AZ. EBS Multi-Attach: io1/io2, one AZ, up to 16 instances.
- Aurora: up to 15 read replicas; auto scaling adds readers only, never a writer.
- ElastiCache Multi-AZ needs 2 nodes; the 3-node minimum belongs to DAX and MemoryDB.
- Full-mesh VPC peering: n(n-1)/2 links (10 VPCs = 45, 100 = 4,950), which is why Transit Gateway exists.
- A VPC has one virtual private gateway; VPN redundancy is two connections with two tunnels each.

## Workflow, ML and cost

- Step Functions Standard: up to a year, exactly-once, billed per transition. Express: up to 5 minutes, at-least-once,
  billed by request and duration.
- SageMaker async inference: up to 1 GB and 1 h per request (between real-time and batch).
- S3 Bucket Keys cut KMS request cost by up to 99%. CloudFront egress is cheaper than serving from S3 directly.
- Cost allocation tags are not retroactive and take up to 24 h to appear. Cost Explorer keeps 12 months.
- Spot: 2 minutes warning; savings 60-70% typical, up to 90%. Graviton: up to 40% better price-performance.

## More figures from Part Three

- Lambda Managed Instances allow up to 90 minutes only for async and event-source-mapping invocations, not synchronous.
- Direct Connect: a transit virtual interface no longer needs a minimum circuit speed (the 1 Gbps figure is stale).
  MACsec is on dedicated connections at higher port speeds, not 1 Gbps. One Direct Connect gateway reaches many Regions,
  up to 20 virtual private gateway and 6 transit gateway associations, and never routes between two transit gateways.
- CloudFront accepts GET, HEAD, OPTIONS, PUT, POST, PATCH and DELETE only, and its certificate must be in `us-east-1`.
- Textract: 1 page synchronous; up to 500 MB and 3,000 pages asynchronous from S3. Comprehend real-time input: 100 KB.
- Trusted Advisor low-utilization check: 10% or less CPU and 5 MB or less network I/O on 4 or more of the past 14 days;
  needs a Business or Enterprise support plan.
- CloudHSM: `hsm2m.medium` is FIPS 140-3 Level 3 (certificate #4703). The older `hsm1.medium` FIPS 140-2 Level 3
  certificate moved to NIST's historical list in January 2026, so "CloudHSM is FIPS 140-2 Level 3" describes retired
  hardware.
- Route 53 Application Recovery Controller spreads its data plane across five Regions so a Regional failure cannot take
  out the thing you depend on during it.
- Stale rules to drop: Firehose "can never be near-real-time" (zero buffering lands records in about 5 s; not for the S3
  backup destination or dynamic partitioning; sub-minute S3 intervals raise request costs). S3 object maximum is 48.8
  TiB, not 5 TB.
