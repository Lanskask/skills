# Operations and Integration

Load this file for questions on infrastructure as code, fleet management, observability, delivery pipelines, backup,
migration, disaster recovery, cost management, queues/topics/buses/workflows, application platforms, IoT/edge and
specialized services, or machine learning service selection.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

## Infrastructure as code and fleet management

- CloudFormation: a template (text file listing resources and relations) creates/updates/deletes resources as one unit,
  a stack.
- Systems Manager operates fleets of servers once they exist.
- Console-clicked infrastructure cannot be reviewed, reproduced or rolled back; templates can be diffed, PR-reviewed,
  applied identically.
- Vocabulary:
  - IaC is the practice; CloudFormation is AWS-native.
  - CDK sits on top of CloudFormation: write in a programming language, synthesizes a template.
  - Terraform is the dominant third-party, multi-cloud alternative (`.tf` files).
  - GitOps: repo is the source of truth; changes arrive by merge, not by someone running a command.
- Not exclusive: CloudFormation knowledge still applies on a Terraform team (what replaces a resource, what a policy
  protects, how stacks span accounts).
- AWS CLI = scripted, not declarative.
  - Fine for a one-off, an investigation, a pipeline step.
  - Wrong when repeatability, drift or review matter: no record of what it created, cannot converge to a known state.
  - CLI performs actions; a template declares desired end state, and only that can tell you something changed
    underneath.
  - Useful CLI features: named profiles with `role_arn` for cross-account work; `--query` (JMESPath) filters output
    server-side.

### CloudFormation mechanics

- Nested stacks: compose templates within one account and Region. StackSets: across accounts and Regions. Crossing
  either boundary makes nested stacks the wrong tool.
- StackSets permission models:
  - Service-managed with automatic deployment reaches accounts added to an OU later.
  - Self-managed needs roles wired by hand in every target account (linear work).
- Capabilities are a safety interlock for templates creating permissions: a template naming IAM resources explicitly
  requires the named-IAM capability; the plain capability is insufficient.
- Stack policy protects resources during updates only, not deletion.
  - Protect data on stack deletion with a deletion policy; `Retain` preserves the resource.
  - `Delete` is already the default, so proposing it for an undeletable non-empty bucket achieves nothing.
  - A lifecycle rule expiring objects does not guarantee the bucket is empty at deletion time.
- Change sets show what an update will do, especially whether a resource is replaced.
  - Replacement is the hidden cause of most unplanned downtime from template changes (an immutable property edited means
    destroy and rebuild).
  - A plain update does this silently.
- Drift detection reports differences only; deploys nothing and does not revert.
- Import existing resources into a stack: bring a VPC under management with no disruption (recreating means outage plus
  re-plumbing attachments, routes, endpoints, peering).
- Governance: grant users permission to run CloudFormation and give the service role the permissions to create
  resources.
  - Granting resource permissions directly to users lets them create things outside CloudFormation.
  - Full CloudFormation access for everyone is not least privilege (admin with extra steps).
- Service Catalog: approved products users launch without holding underlying permissions (launch constraints supply
  them). Governs what may be provisioned; gives no pricing discount.

### Systems Manager

- Tools to operate servers (AWS or on-premises) at scale without logging in individually; an agent on the instance does
  the work; address instances by tag, not name.
- Parameter Store: configuration and secure strings.
- Patch Manager: patch baselines on a schedule plus compliance reporting. Scalable fleet-wide vulnerability answer when
  run from a delegated administrator targeting by OU and tag.
- Automation: runbooks (multi-step operational procedures).
- Session Manager: audited shell access.
- Inventory and State Manager: record and enforce what is installed.
- Boundaries:
  - Patch Manager deploys patches; not a vehicle for installing arbitrary assessment tooling across a fleet.
  - A VPC endpoint for Systems Manager is needed only for instances with no internet path; with an existing route out it
    will not fix connectivity.
  - The Chef/Puppet-based configuration-management service is not a patching or vulnerability tool.
- AppConfig: application config and feature flags as a deployed artifact; validated before release, gradual rollout,
  automatic rollback on alarm. Alternative (config baked into deployment) makes every flag change a deployment.
  - A feature flag changes behavior in existing code; it is not a release mechanism for code that does not exist.

## Observability and delivery pipelines

### Logs, metrics and traces

- Log: timestamped record of an event. Metric: number over time (cheap to store and alarm on). Trace: follows one
  request across services.
- Which question:
  - "Is the system healthy?": metric.
  - "Why did this request fail?": log.
  - "Which of eleven services is slow?": trace (essentially unanswerable without tracing beyond a few services).
- CloudWatch Logs = logs; CloudWatch metrics = time series; X-Ray = tracing.
- X-Ray is distributed tracing only: not a unit-test framework, not static analysis, does not ingest arbitrary data
  streams. "Service maps" is X-Ray vocabulary; metrics alone do not build them.
- Logs Insights uses its own query language, not SQL.
- Metric filters turn a log pattern into a metric to alarm on (no scheduled grep function needed).
- Subscription filters stream logs near real time to a data stream, delivery stream or function, not to a queue.
  Periodic export to object storage is batch and fails a near-real-time requirement.
- Composite alarms:
  - Fight alarm fatigue; have no metric of their own, a boolean expression over other alarms (e.g. page only if
    error-rate AND health-check alarms are both in ALARM).
  - Supported way to cut noise without raising thresholds (which hides real problems).
  - Can suppress children via an actions-suppressor (e.g. a maintenance window or active deployment alarm).
- Cross-account observability:
  - Default: logs/metrics/traces visible only inside their account.
  - Designate a monitoring account and link source accounts for one place to search logs, query metrics, view traces;
    data stays where it is.
  - Alternative of shipping all logs via subscription filters works but costs more, duplicates storage, and loses
    metrics and traces.
- Managed Grafana + Managed Service for Prometheus: for orgs already on Prometheus/Grafana (often Kubernetes, often
  multi-cloud) that do not want to rewrite dashboards and alert rules for CloudWatch. Prometheus = ingestion and PromQL;
  Grafana = dashboards and data-source federation (including CloudWatch). Pick them for existing Grafana dashboards,
  PromQL, or hybrid/multi-cloud viewed in one place.
- Memory and disk are not default instance metrics; both need the agent (hypervisor cannot see inside the guest).
- Status checks detect a sick instance, not a dead application process; process monitoring needs the agent or a custom
  metric.
- Load balancer access logs record HTTP requests, not what the application logged internally.

### Audit trail

- Records API calls (who, what, when, from where, success). Not data-plane traffic: not network flow logs, not
  file-transfer contents, not what happened inside an SSH session.
- Object-level access needs data events, enabled explicitly; management events (default) do not cover them.
- Organization trail covers every account including later-created ones (per-account trails are the overhead it removes).
- Notification specific to a particular API event: use an event rule matching that event, not a notification on the
  whole trail.
- Fastest to implement threat detection: a purpose-built threat-detection service beats a hand-written rule.
- CloudTrail Lake: queryable store with its own SQL interface, retention in years; removes the export-to-S3 plus Athena
  arrangement.
- Log file integrity validation: signed digest proving the trail is unaltered; neither bucket versioning nor Object Lock
  fully answers this.
- Compliance services:
  - Artifact: self-service portal for AWS's own audit evidence (SOC reports, ISO/PCI certifications, agreements such as
    a business associate addendum). "Prove the platform is compliant."
  - Audit Manager: evidence about your workloads against a framework.
  - Config: whether resources match your rules.
  - Security Hub: aggregates findings.
  - Brief asking for the auditor's copy of a SOC 2 report wants Artifact only.

### The delivery toolchain

- CodeCommit: Git repos (check). CodeBuild: compile/test. CodeDeploy: push releases to instances, containers or
  functions. CodePipeline: orchestrates stages. CodeArtifact: package dependencies. CodeGuru: reviews code for defects
  and profiles running apps for expensive code paths.
- Gap: source-control repositories are not covered by the managed backup service and have no snapshot concept.
- CodeArtifact upstream repository: proxies and caches the public registry for a build environment with no internet.
  - A NAT gateway gives the whole VPC internet access, contradicting isolation.
  - Hand-mirroring dependencies into source control is unmanageable at scale.

### Deployment

- In-place: instances out of service during update; rollback means redeploying (slow during an incident).
- Blue/green: old environment intact; rollback is a traffic switch.
- "Push another update" is not a rollback strategy.
- Baking an image and replacing instances takes minutes; fails a requirement to deploy several times an hour. Match
  mechanism to frequency.
- Where dashboards already exist in a third-party tool, the managed version of that tool preserves investment and
  features; rebuilding natively throws both away.

## Backup, and knowing what is covered

- The managed backup service centralizes plans across services and accounts; vaults are the storage boundary; one place
  to confirm backups ran (vs checking nine consoles).
- Design-deciding details:
  - Cross-account copy needs a vault in both accounts.
  - Vault lock gives write-once retention in the destination, surviving a compromised administrator.
  - Cold storage has a minimum retention of ninety days; moving data you will delete sooner costs more.
- Knowing which services it does not cover is as valuable as knowing which it does (e.g. source-control repos, see
  delivery toolchain).

## Migration and disaster recovery

### Discovery before migration

- Three tools; the requirement says which starting condition applies.

| Tool                          | Use when                                             | Notes                                                                                                                                                                                                   |
| ----------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Application Discovery Service | No reliable inventory; need network and process deps | Agentless collector: VM inventory and performance only, no network connections or process dependencies. Needing those forces agent-based. No-install rule or thousands of machines points to agentless. |
| Migration Hub                 | Already have inventory data                          | Central tracking; CSV import of server inventory; right-sizing recommendations and exportable cost estimates.                                                                                           |
| Migration Evaluator           | Business case                                        | TCO for budget approvers.                                                                                                                                                                               |

- Execution tools (server-migration or database-migration service) run migrations; they produce no dependency diagrams
  and no cost case.

### The migration strategies

- Taxonomy: rehost (lift and shift), replatform (lift and reshape, e.g. managed database), repurchase, refactor, retire,
  retain.
- Speed and minimal disruption: rehost. Escape license and operational cost: replatform.
- Check "refactor" against any constraint ruling out code changes; refactoring is impossible without source code.
- First workload (AWS guidance): low-risk, loosely coupled, not business-critical, rehosted not re-architected. Leading
  with a tightly coupled core or latency-critical platform is the anti-pattern.
- Application Migration Service: rehosts servers via continuous block-level replication with short cutover. Does not
  migrate managed databases (that is DMS).
  - Without the "use private IP for data replication" setting, replication traffic goes to public service endpoints even
    when a private connection exists.
- App2Container: inspects a running Java or .NET app, containerizes it, generates deployment artifacts; containerize
  with no code change.
- VM Import/Export: older, lower-level; image file to AMI, or back out, in a single operation.
  - Use for golden templates, vendor OVA appliances, exporting back on-premises for a contract, avoiding lock-in or
    handing a workload back.
  - Application Migration Service instead for live production (continuous replication, minutes of downtime).
  - Import/export requires the source shut down and exported first: maximum downtime; fine for dormant systems, wrong
    where outage is forbidden.
  - Detaching database files and in-place engine upgrade also require outages.
- DMS + Schema Conversion Tool:
  - DMS moves data; change data capture keeps source live until cutover (near-zero-downtime). Handles homogeneous moves
    alone.
  - SCT handles heterogeneous: converts tables, views, stored procedures, application SQL between dialects; produces an
    assessment report of what cannot auto-convert.
  - Oracle to Aurora PostgreSQL: SCT + DMS. Oracle to Oracle on RDS: DMS only. DMS alone for an engine change has no
    answer for stored procedures.

### Disaster recovery strategies

| Strategy                 | Description                                               | Recovery time |
| ------------------------ | --------------------------------------------------------- | ------------- |
| Backup and restore       | Restore from backups                                      | hours         |
| Pilot light              | Minimal core (usually database) always on, rest on demand | between       |
| Warm standby             | Scaled-down functioning copy, scaled up on failover       | between       |
| Multi-site active-active | Full capacity in both                                     | near zero     |

- Order is increasing cost and decreasing recovery time.
- RTO: how long you may be down. RPO: how much data you may lose. A design must state both.
- The stated objectives select the strategy; over-delivering loses on cost as surely as under-delivering loses on
  availability (a global database for an RPO of hours is the right architecture for the wrong question).
- Eliminations:
  - A runbook deploying the stack at failure time cannot meet an RTO of minutes; neither can restoring a large snapshot.
  - Scheduled backups cannot meet an RPO of seconds or minutes; that needs replication.
- Failback: a copy or sync tool has no automated route home; a purpose-built recovery service does. Most plans never
  write down how to get back.

### Verifying recovery, which most designs skip

- Resilience Hub: assesses an app against declared recovery objectives, returns a score, recommends fixes. The service
  for "validate that the design meets its objectives".
- Fault Injection Service: controlled experiments (terminate instances, inject latency, fail over a database) with
  guardrails and a stop condition; runnable against production.
- Route 53 Application Recovery Controller:
  - Readiness checks: continuously audit whether standby could take over.
  - Routing controls: manual on/off switches with a safety rule set (cannot turn everything off by accident).
  - Zonal shift: moves traffic away from one impaired AZ.
  - Data plane spread across five Regions to keep working during the events you need it for.

## Cost management

- Cost is a design constraint; every engineer spends continuously, usually without seeing a price.
- Services:
  - Cost Explorer: spend and trends.
  - Cost and Usage Report: detailed line-item dataset, for questions a dashboard cannot answer.
  - Budgets: threshold alerts.
  - Cost Anomaly Detection: unusual patterns, no number specified.
  - Compute Optimizer: right-sizing.
  - Trusted Advisor: best-practice checks.

### Commitments

- Reserved Instances commit to a specific configuration; Savings Plans commit to an hourly spend.
- Compute Savings Plan: covers EC2, Fargate and Lambda; flexes across instance family, size and Region.
- EC2 Instance Savings Plan: cheaper, locked to one instance family in one Region. Serverless containers/functions or a
  flexibility requirement rule it out regardless of discount.
- A commitment changes the price, never the size of what you run. Savings Plans are not right-sizing; right-sizing is
  not a discount. Two independent levers; committing to an oversized fleet locks in waste for a year.
- Do not size a reservation to the peak of a spiky workload; cover the steady baseline and let variable capacity absorb
  peaks. Renewing on mostly idle capacity perpetuates the mistake.
- Buy in the management account with sharing enabled, not in each member account (prevents sharing). No policy controls
  discount sharing: it is a billing preference in the management account, not an access-control action, so no
  organization policy expresses it.

### Allocation and visibility

- Cost allocation tags: activate in the management account; activation only makes an existing tag visible in billing, is
  never retroactive, takes up to 24 hours. The tag must already be on resources.
- Tags work at resource granularity: tenants sharing one resource rule tagging out (cannot attribute a fraction of a
  shared table). A billing-view service with custom pricing handles chargeback.
- A member-account report cannot give an organization-wide view.
- A monitoring dashboard cannot visualize the billing dataset directly; that needs a query engine plus visualization
  tool (a pipeline, not a setting).

### Alerting

- Budget needs a fixed amount (re-entered continuously to track a moving average).
- Billing alarm needs a static threshold and says only that spend rose, never which account or resource.
- Detecting unusual spend rather than spend above a number: anomaly detection (learns the baseline).

### Right-sizing

- Compute Optimizer: recommendations for instances, volumes, functions, ECS services on Fargate (including task sizing).
  Enhanced infrastructure metrics are paid and instance-only, not a free universal upgrade.
- Trusted Advisor cost checks need a Business or Enterprise support plan (check). It has no billing breakdown by tag, no
  budget threshold alerting, no scheduled export.
- A custom pipeline for right-sizing recommendations re-implements an existing feature; per-account gathering multiplies
  work.
- Price list API returns public list prices, never your negotiated spend ("what does this cost", not "what did we pay").

### Spot

- Deep discount; can be reclaimed with two minutes' notice.
- Requirement language giving permission: not critical, can be reprocessed, fault tolerant, reruns next cycle.
- Fails an availability requirement; never right for a license server, primary database, live user session, or a node
  holding the only copy of cluster state.

## Application integration: queues, topics, buses and workflows

- Purpose: decouple so one slow or broken component does not take down others (direct synchronous HTTP lets a slow
  dependency propagate upstream and fill threads).
- A queue between them: producer writes and returns; consumer drains at its own rate; outages just make messages wait.
- Cost: synchronous answer traded for eventual one; caller no longer knows the outcome. Designs needing an immediate
  answer cannot simply be queued; otherwise failures are invisible rather than absent.
- The four:
  - Queue (SQS): buffers work for consumers to drain at own pace.
  - Topic (SNS): broadcasts one message to many subscribers.
  - Event bus (EventBridge): routes events by content.
  - State machine (Step Functions): multi-step workflows with retries and error handling.
- Also: Amazon MQ (managed ActiveMQ/RabbitMQ broker, only for existing apps speaking JMS, AMQP or MQTT that must not be
  rewritten); Amazon AppFlow (moves data between SaaS apps and AWS on schedule or event, e.g. Salesforce to data lake as
  configuration).

### Choosing between them

- Queue: point-to-point, one message one consumer. Wrong when several services need the same event (first reader takes
  it).
- Topic: fan-out, copy per subscriber, but pushes and does not buffer; a down subscriber loses the message. Wrong when
  consumers drain at own pace or retry later. Delivers to queues, functions, HTTP endpoints, email, SMS (also last hop
  in alerting).
- Core pattern: topic fanning out to a queue per consumer; each gets a durable copy, drains independently, adding a
  consumer adds a queue without changing the publisher. Use whenever several services (including other accounts) need
  the same event.
- Event bus: routes on payload content to different targets. Not a work queue you drain at your pace; if no target
  succeeds the event is gone.
- Direction is fixed: topics publish to queues, never the reverse.
- Stream: ordered, replayable, high-volume analytics data. Discrete transactional work (order, payment, signup) belongs
  in a queue, not a stream.
- Event-driven beats scheduled: where the source can emit an event, react rather than poll. If a stated cadence such as
  "once daily" is itself the complaint, keeping it keeps the problem.

### Queue mechanics

- Standard: at-least-once delivery, best-effort ordering, effectively unlimited throughput.
- FIFO: exactly-once processing, strict ordering.
  - Default mode: about 300 transactions per second per API action per partition, roughly 3,000 messages per second with
    batching.
  - Old advice "FIFO cannot scale" is out of date: high throughput mode gives 70,000 transactions per second in the
    largest Regions, ten times that with batching, lower elsewhere.
  - Ordering works through message group IDs, so throughput needs many groups, not one.
- Visibility timeout must exceed processing time, or a second consumer processes in-flight work twice (most common
  misconfiguration).
- Long polling reduces empty receives and their cost.
- Dead-letter queue: captures repeatedly failing messages (poison message does not block). Type must match the source (a
  FIFO DLQ cannot serve a standard queue); max receive count of zero is invalid.
- Scale consumers on queue depth, not CPU. The oldest-message-age metric measures age, not volume: wrong for scaling on
  backlog (one stuck message makes it climb forever).
- A queue in front of a burst makes work re-runnable and scaling honest; traffic straight into compute with no buffer
  can be dropped in a spike (a dropped message is a lost order).

### Workflow orchestration

- Use a state machine when a process has more than about three steps, each can fail and needs different retry policy;
  coordination moves from code to a visible definition.
- Standard workflows: up to a year, exactly-once, full execution history, billed per state transition.
- Express workflows: up to five minutes, at-least-once, billed by request and duration; high-volume event processing at
  a fraction of the cost.
- Callback pattern (task waits for a token): pauses up to a year with no compute running; the answer for human approval
  or external callbacks; beats polling loops and sleeping functions on cost and reliability.
- Error handling: catch-all requires the catch-all error name, not only the runtime error (a one-class catch lets other
  classes through).
- A function chain coordinated by "when the queue is empty" is fragile; use a state machine.

### Smaller services that answer specific requirements

- EventBridge Pipes: point-to-point (source, optional filter, optional enrichment, target); removes glue functions
  between a stream and its consumer.
- EventBridge Scheduler: one-time and recurring schedules at very large scale with time zones and retry policies; beats
  a rule for millions of independent schedules (e.g. one per customer).
- AppSync: managed GraphQL with subscriptions pushing to clients. For real time; polling every few seconds is the
  anti-pattern; caching makes data staler.
- Amazon MQ: managed traditional broker for apps already on AMQP, MQTT or STOMP and not being rewritten. Existing
  standard protocol and no code change: managed broker; new build: native services.
- Channel vs audience:
  - SNS: operational plumbing (alerts to teams, messages to systems).
  - Pinpoint: campaigns, push, user messaging with segmentation, scheduling, A/B testing, engagement analytics. AWS
    closed it to new customers May 2025, end of support 30 October 2026, channels moved to AWS End User Messaging
    (check). Use End User Messaging now.
  - Pinpoint for internal alerting, or SNS as a customer communication platform, means fighting the tool (SNS can text
    but has no customer, segment or open tracking).
  - One-way text messaging cannot carry a two-way conversation or survey (different product).
- Mismatches: batch operations over object storage run against a manifest of existing objects, not queue messages;
  archival storage is a storage class, not failure handling; email is not a work queue.
- Warning: resizing a file in place and replacing the original destroys the source and prevents rerun; check the
  original survives.

## Application platforms

- Services that run your application and make infrastructure decisions; between "here is a server" and "rewrite as
  functions". For a small team that does not want to become an infrastructure team; loss of control only matters if you
  need it.
- Elastic Beanstalk: deploys and manages an app on instances you still own (provisioning, load balancing, scaling). Not
  serverless; that word rules it out.
  - A database created inside a Beanstalk environment is deleted with the environment; keep anything durable outside it.
  - CNAME swap is first-class blue/green: deploy to a second environment and swap, no manual DNS editing.
  - Deployment policies: all-at-once (development only), rolling, rolling with additional batch (full capacity
    throughout), immutable (new instances alongside old; safest rollback).
  - Before creating a new application or environment, check whether the existing one can be reconfigured in place.
- App Runner: container image or source repo as a scaling web service with a URL; builds from source on commit,
  provisions TLS, scales up and down; no visible cluster, load balancer or task definition.
  - Cannot be registered as a load balancer target (front door or nothing).
  - Request-response web services only; background workers and scheduled jobs belong elsewhere.
- Amplify: hosting with continuous deployment plus built-in auth and storage integration for front-end and full-stack
  apps.
  - Versus App Runner: which half you deploy; Amplify is static/server-rendered front end with managed back-end
    resources (Cognito user pool, AppSync API, DynamoDB table) wired by convention.
  - Branch-based preview environments: every pull request gets its own URL.
- Lightsail: simplified fixed-price hosting for small predictable workloads (instance, storage, transfer allowance in
  one monthly price).
  - No Auto Scaling groups, no load balancer targets outside Lightsail, limited AWS integration; outgrowing it means
    migrating.
  - Fine for a WordPress site or internal tool that never grows; for anything expected to scale it is a scheduled
    migration.
- Proton: platform-team templates developers deploy into; self-service infrastructure conforming to standards. Service
  catalog governs what may be provisioned; Proton shapes how applications are deployed.
- Anti-patterns:
  - Running a database in a container beside the app loses backups, failover, patching.
  - Modernization means replacing self-managed components with managed ones (static content to object storage plus CDN,
    search to managed search, database to managed engine); re-hosting self-managed engines as containers you operate is
    a lateral move.
- Hard constraint: refactoring is impossible without source code; where none exists, rehosting is the only option.

## IoT, edge and specialized services

- IoT family: millions of small, unreliable, intermittently connected devices, each with its own identity, over a
  protocol for constrained networks.
- Why web architecture does not transfer:
  - Each device needs its own cryptographic identity (shared credential across a million devices is worthless after one
    compromise).
  - Devices are offline for hours and must behave sensibly on return.
  - Messages are a few dozen bytes over metered radio; HTTP header overhead can exceed the payload.
- MQTT: publish-subscribe protocol with tiny framing, built for these conditions.
- IoT Core: managed MQTT at scale, per-device X.509 certificates, rules engine routing to other services with SQL-like
  filter.
  - Alternatives that fail: Kafka and traditional brokers (no per-device certificate identity at fleet scale); ALB (HTTP
    only, cannot front MQTT); self-run broker on instances (patching, scaling, certificate lifecycle for a million
    clients).
- Device shadow: JSON document in the cloud holding reported and desired state.
  - App writes desired state and returns; device receives the delta on next connect and reconciles; neither side blocks.
  - A backend calling a device directly and waiting misunderstands the problem.
- Onboarding: registering a thing at manufacturing enables it months before installation (a stolen device is a live
  credential). For devices that must stay inert until installed, use just-in-time provisioning with a pre-provisioning
  hook (validate and register at first connection).
- Bursty device traffic into a database: an IoT rule targets a data stream to absorb the spike (buffer first, then
  process). A function invocation per message every few seconds costs far more than one buffered batch.
- Basic Ingest: messages go straight to the rules engine, bypassing the message-broker charge. Applies when no other
  applications subscribe to the device topics.
- Greengrass: runs at the edge for local processing and offline operation; not a cloud ingestion endpoint. With a model
  compiler it runs inference with no connection, ruling out cloud-endpoint designs for offline work.
- Rest of the family:
  - Device Defender: audits fleets, detects behavioral anomalies.
  - Device Management: onboarding at scale, over-the-air updates.
  - IoT Events: pattern detection across sensors; AWS ended support May 2026, use IoT Core rules or a stream processor
    (check).
  - SiteWise: industrial equipment data over OPC-UA.
  - TwinMaker: digital twins.
  - IoT Things Graph: visually wires devices and web services into a flow without code, for when integration is the
    whole project.
  - IoT 1-Click: simple pre-provisioned button or sensor triggers a Lambda function; signal is a single-purpose physical
    trigger with no device software.
  - Monitron: turnkey sensors plus managed predictive maintenance on rotating equipment, no model of your own; wrong the
    moment you need to deploy your own model.
- Edge placement: Outposts = AWS hardware in your own data center; Local Zones = compute near a metropolitan area;
  Wavelength = inside a telecom network (mobile edge). Own data center: Outposts; mobile network: Wavelength; a factory
  floor is neither Local Zones nor Wavelength.
- Elemental MediaConvert: file-based video transcoding (format conversion, adaptive bitrate packaging, captions);
  managed replacement for Elastic Transcoder and encoding-tool instance fleets.
- Managed Blockchain: Hyperledger Fabric and Ethereum networks without operating nodes; for a distributed ledger shared
  between organizations, not a database with an audit trail.
- GameLift: dedicated game server fleets with matchmaking and session placement across Regions; signal is player
  sessions, match placement, low-latency server allocation (a general load balancer cannot express these).
- Communications:
  - Connect: cloud contact center; quick connects handle natively what a custom control panel would be built for.
  - SES: email; delivery, bounce and complaint events come from configuration sets with event destinations, not the API
    audit trail (which records only the send call).

## Machine learning, and what it is actually used for

- ML here is service selection under a constraint, not modeling: does a managed service already do the task, and which
  one.
- Custom model = collect data, label, train, evaluate, deploy, monitor drift, retrain: a long commitment by a specialist
  team. A managed service is an API call; weaker on your edge cases, better on everything else, and already exists.
- Generative AI (managed foundation models, assistants, agents) sits alongside, not replacing: text generation,
  summarization, conversation over your data. For classification, extraction and recognition, purpose-built services
  remain cheaper, faster, more predictable; compare before reaching for a general model.

### The managed catalog

| Service        | Does                                                                       |
| -------------- | -------------------------------------------------------------------------- |
| Rekognition    | Images and video: objects, scenes, faces, moderation, text in a photograph |
| Textract       | Documents: OCR plus form fields as key-value pairs and tables as cells     |
| Comprehend     | Text: entities, sentiment, language, topics, PII                           |
| Transcribe     | Speech to text                                                             |
| Translate      | Machine translation                                                        |
| Polly          | Text to speech                                                             |
| Lex            | Conversational interfaces                                                  |
| Kendra         | Intelligent enterprise search with managed connectors                      |
| Personalize    | Recommendations                                                            |
| Fraud Detector | Online fraud scoring                                                       |
| SageMaker      | Build, train and deploy your own model                                     |

### The distinctions that actually matter

- Textract vs Rekognition: Rekognition text detection finds words in a photo (sign, box label, number plate); Textract
  understands document structure (field values, table rows, headers). Rekognition on a scanned invoice returns a bag of
  words with no idea which is the total. Documents: Textract; photographs: Rekognition.
- Kendra vs OpenSearch: OpenSearch is an index you build, populate and tune (full relevance control). Kendra has managed
  connectors (SharePoint, S3, Salesforce, Confluence, etc.), natural-language answers, no tuning. For repositories you
  do not own or cannot restructure, Kendra takes a day vs a quarter.
- Comprehend vs Macie: Macie finds sensitive data at rest in S3 buckets; Comprehend inspects any text handed to it,
  including in flight (only one usable in a request path). Redact before storing: Comprehend. Audit what the estate
  already holds: Macie.
- Transcribe plus Comprehend: canonical contact-center pipeline (speech to text, then sentiment and entities); a design
  naming only one has solved half.
- Build vs buy: managed service almost always. SageMaker earns its place for tasks particular to your business (pricing
  your inventory, scoring your risk, predicting your equipment failure), not sentiment, transcription, translation or
  object detection.
- Where the rule can be written down, write it (regex, Config rule, firewall rule): cheaper, faster, explainable, always
  correct. ML is for rules you cannot express.
- Clinical variants Comprehend Medical and Transcribe Medical: separate products trained on medical vocabulary for
  patient data; use for healthcare instead of the general versions.

### Limits worth carrying

- Document extraction: one page synchronously. Multi-page PDFs need the asynchronous API, which reads from object
  storage (cannot stream a large document at the API). Async PDFs up to 500 MB and 3,000 pages.
- Language support is uneven:
  - Text detection and most analysis: more than 40 languages, including Chinese, Japanese, Korean, Arabic, Hindi.
  - Forms (key-value pairs) limited to English, Spanish, Italian, Portuguese, French, German.
  - Handwriting: English only.
  - Reads horizontal text at any rotation but not vertical text (disqualifies some Asian-market pipelines).
  - Identity-document feature: US passports and driver's licenses only.
- Text analysis can redact only as an asynchronous batch job. Real-time analysis returns entity offsets and types, not
  redacted text; for synchronous masking, redact in your own code using the offsets.

### Deployment choices for your own models

- Decision is the endpoint type that fits the traffic:
  - Real-time endpoint: interactive, low latency, steady traffic; bills for always-on instances.
  - Serverless inference: idle periods between bursts; tolerates cold starts.
  - Asynchronous inference: large payloads and long processing (up to 1 GB, up to one hour per request) via queueing;
    can scale to zero between requests. Easy to miss: "payload too large for real-time" plus "takes several minutes" is
    exactly its case.
  - Batch transform: whole dataset offline, no endpoint left behind.
- A single real-time endpoint can host multiple production variants with weighted traffic to compare two models on live
  traffic without a second endpoint or client change.
