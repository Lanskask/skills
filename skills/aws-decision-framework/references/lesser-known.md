# Lesser-known services

Load when a requirement names a narrow job (transform on read, fine-grained lake permissions, SaaS data import, feature
flags) and the headline services do not fit. Each exists because nothing else does its job.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

- **S3 Object Lambda**: transforms an object as it leaves a read (redact, resize, reformat) with no second stored copy.
  Use it when consumers need different views of one object.
- **S3 Inventory**: scheduled report of every object and its metadata; the way to audit or reconcile a bucket with
  millions of objects without listing it.
- **RDS and Aurora blue/green deployments**: a synchronized staging copy for engine upgrades and schema changes;
  switchover is typically under a minute and blocks writes only during the switch. It guards against an upgrade that
  succeeds but turns out incompatible, because the old environment stays intact.
- **Lake Formation**: permissions down to database, table, column, row and cell on the Glue Data Catalog, with tag-based
  access control. Bucket policies and S3 access points are coarser and cannot express column or row rules.
- **Athena federated query**: connectors reach non-S3 sources (relational, key-value, on-premises) from one SQL
  interface without first building a pipeline to centralize the data.
- **Serverless analytics variants** (Redshift Serverless, EMR Serverless, MSK Serverless, OpenSearch Serverless,
  ElastiCache Serverless): remove capacity planning. Pick them when load is unpredictable and nobody wants to run a
  cluster.
- **Security Lake**: centralizes AWS, on-premises and partner security data in an open schema, so tooling needs one
  integration instead of one per source.
- **Well-Architected Tool**: reviews a workload against the six pillars and outputs an improvement plan; a cheap
  architecture exercise that is rarely run.
- **Managed Service for Prometheus** (with Managed Grafana): container metrics at scale with no servers; beats
  rebuilding dashboards on CloudWatch for teams already on that toolchain.
- **AWS Health Dashboard**: events affecting your resources specifically, emitted as events you can automate against
  (instance retirement, certificate expiry trigger an action instead of an email).
- **AWS Proton**: self-service infrastructure templates so developers deploy into a governed stack. It shapes how apps
  deploy; Service Catalog governs what may be provisioned at all.
- **Amazon AppFlow**: no-code scheduled or event-driven data movement between SaaS apps and AWS; usually beats a
  function calling the SaaS API on a timer.
- **AWS AppConfig**: configuration and feature flags as a validated, gradually deployed artifact with automatic
  rollback, so a flag change is not a deployment.
- **AWS Device Farm**: tests mobile and web apps on real physical devices.
- **Cognito user pool vs identity pool**: a user pool is a directory that authenticates and returns tokens; an identity
  pool exchanges a token (user pool, Google, corporate provider) for temporary AWS credentials so the app can call AWS
  as that person.
