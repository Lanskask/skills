# AWS compute: EC2, Auto Scaling, Lambda, containers

Load this file when choosing or reviewing AWS compute: EC2, Auto Scaling groups, Lambda, ECS/EKS/Fargate, Batch or the
container registry.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

## EC2: virtual machines, and where they physically land

- EC2 = virtual machine you fully manage (size, OS image, network location). In practice it is an umbrella: images
  (AMIs), block volumes, elastic IPs, security groups, load balancers.
- Baseline for all compute: max control, max responsibility. Pick it for a specific kernel, licensed software that must
  see real hardware, or an app nobody will rewrite.
- Reflex: if a managed service does the same job, EC2 usually loses. Self-managed DNS forwarders, mail servers, MQTT
  brokers, file transfer servers, Kubernetes control planes, document databases, image-analysis libraries all have
  managed equivalents that win when the goal is less ops work.
- Counter-case: EC2 is the least locked-in option. Static instances move to another provider easily; lock-in starts with
  autoscaling, custom imaging and platform tooling (usually worth it, but a choice).
- Region is a first-order choice, often inherited from the console default. Three variations:
  - not every service exists in every Region
  - baseline prices differ roughly 10-30%
  - data residency rules may decide it outright
- Pick the Region deliberately at the start; finding out a year later that a needed service is missing where the data
  lives is expensive.

### Placement groups

- A placement group influences which physical hardware instances land on. Three strategies cover almost all cases, a
  fourth is narrow.

| Strategy       | Layout                                                                                                 | Use for                                                                                                                                  | Cost or limit                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Cluster        | Close hardware, one AZ, high-bandwidth low-latency network                                             | Tightly coupled HPC, distributed in-memory DBs, constant node-to-node chatter                                                            | Single AZ: failure domain deliberately concentrated                                                            |
| Spread         | Each instance on distinct hardware                                                                     | Few individually critical instances (license servers, controller quorum)                                                                 | Max 7 per AZ per group                                                                                         |
| Partition      | Groups of instances in partitions, each on own racks (own power and network)                           | Large rack-aware systems: HDFS, HBase, Cassandra                                                                                         | Max 7 partitions per AZ; group exposes instance-to-partition mapping so the app can decide replication         |
| Precision time | Hardware with direct access to high-accuracy time sources (PTP hardware clock), microsecond clock sync | Distributed DBs ordering transactions by timestamp, financial systems proving when something happened, reconciling events by local clock | No extra cost; a cluster placement group can be created as its child (tight network plus precise time) (check) |

- Capacity error when adding instances to an existing cluster placement group: stop and start every instance in the
  group so AWS re-places the whole group on hardware with room for all. Placement groups cannot be merged; adding one
  instance at a time keeps failing.

### Choosing an instance family

- Type name = family letter (CPU-to-memory ratio) + generation number + size suffix.

| Family   | Meaning                                                                       |
| -------- | ----------------------------------------------------------------------------- |
| `C`      | Compute-optimized: most CPU per unit of memory                                |
| `R`, `X` | Memory-optimized: in-memory DBs, large caches                                 |
| `M`      | General purpose: the default when nothing in the requirement points elsewhere |
| `T`      | Burstable: accrues CPU credits idle, spends them in spikes                    |

- `T` is good for low average utilization with occasional bursts; poor for sustained load. When credits run out it
  throttles to baseline, which looks like a mysterious performance cliff.
- Graviton (AWS ARM) gives materially better price-performance than x86. If the workload can be recompiled (for
  interpreted languages often just a base image change), it is one of the few levers that cuts cost without cutting
  capacity.
- Instance-type tables hide two things:
  - some network performance is a vague label ("Low", "Moderate", "Up to 10 Gigabit"); "up to" means burst, not
    sustained
  - the official type list is hard to read; practitioners use community comparison sites with price and spec in one
    sortable table
- Right-sizing: change size before family. Example: `r6g.16xlarge` at 25% utilization becomes `r6g.4xlarge`, not a
  `c6g`; someone chose the memory-heavy ratio for a reason. Changing family needs evidence, not just a utilization
  graph.
- Memory is NOT a default EC2 metric (hypervisor cannot see inside the guest). Memory-based right-sizing or alarms
  require the CloudWatch agent on the instance.

### Reserving capacity, and the trap inside it

- On-Demand Capacity Reservations hold capacity in a specific AZ for a specific instance type so launches are
  guaranteed. They are a capacity guarantee, not a discount; the billing discount is a separate construct (often
  conflated).
- Trap: a reservation is zonal. Putting it all in one AZ recreates the single point of failure that multi-AZ was meant
  to remove. If the design must survive losing a zone, spread reservations across zones too (costs more). A reservation
  in the zone that just failed guarantees nothing.

### Getting a shell without opening a port

- Old pattern: bastion host in a public subnet with SSH open to the world. The alternatives differ in what gets
  recorded.

| Option               | How it works                                                                                                                     | What it records / when to pick                                                                                                                                                                     |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Session Manager      | Shell with no inbound port, no SSH key, no bastion. Needs SSM agent and the managed-instance-core policy on the instance profile | Logs the whole session to S3 or CloudWatch Logs. The only option that records session content: pick for audit of commands run                                                                      |
| EC2 Instance Connect | Pushes a one-time public key valid about 60 seconds via an API call                                                              | CloudTrail records the key-push API call, not the SSH session; still uses port 22. Pick for unique key per instance plus a record of who requested access. Does NOT satisfy command-level auditing |
| Fleet Manager        | Browser-based remote desktop for Windows instances                                                                               | No bastion, no gateway server                                                                                                                                                                      |

- Storing SSH keys in a secrets manager is not a third option: it only changes where the key lives. The key stays
  long-lived and the SSH session still generates no audit event. An access-auditing requirement is not met by better key
  storage.

### Networking and imaging details that bite

- Disable the source/destination check on instances that forward traffic they did not originate: NAT instances, proxies,
  routers, virtual firewall appliances. Enabled (the default), the instance silently drops packets whose source or
  destination is not itself; symptom is traffic vanishing with no error.
- MAC address belongs to the network interface, not the instance. For MAC-licensed software, pre-provision a pool of
  network interfaces and attach the right one at boot; do not try to pin an instance.
- Image rule: bake the software, never the specifics. License keys, IP addresses, vendor tokens in an image force
  rebuild and redistribution on every change across every Region used.
- Worse: obtaining a license at launch time from a vendor that takes hours to issue it. That destroys autoscaling, since
  new capacity must be useful within minutes.
- Creating an image from a running instance reboots it by default. If the app must keep serving, use the no-reboot
  option, trading filesystem consistency for availability.
- EC2 Image Builder turns imaging into a pipeline:
  - a recipe = base image plus build and test components
  - produces hardened, versioned images on a schedule, distributes to nominated Regions, shares with needed accounts
  - why: hand-built images drift (one patched, another forgotten; unknown contents in production; rarely used Region
    three CVEs behind)
  - pick it for a golden image, consistent hardening across accounts, or compliance evidence of what is installed ("we
    patch our AMIs" as a fact, not a claim)

### The metadata service, and the attack it enables

- Every instance can reach link-local `169.254.169.254`: instance ID, network config, and temporary credentials for the
  attached IAM role. This is how instances authenticate without stored keys.
- It is the single most exploited path into an AWS account, via server-side request forgery (SSRF): an app tricked into
  fetching an attacker-supplied URL (image resizer, webhook validator, PDF renderer following links) fetches the
  metadata address and returns the role credentials. No shell or exploit chain needed.
- Fix: IMDSv2, enforce everywhere.
  - requires a session token obtained by a PUT request before any metadata read
  - the token response carries a low IP hop limit
  - together they break the attack: forged request is almost always a simple GET, and the hop limit stops a token
    leaking through a container network or proxy
  - set instance metadata options to required (not optional), bake into launch templates, enforce org-wide with a
    service control policy that denies `ec2:RunInstances` when metadata v1 is permitted
- Related judgments:
  - disabling the metadata service entirely is stronger than IMDSv2 and suits instances needing no AWS access, but it
    breaks the Systems Manager agent and most monitoring agents, so it is rarely practical
  - restricting metadata with host firewall rules is a workaround that fails when someone rebuilds the instance
  - an over-permissioned role defeats all hardening: IMDSv2 protects the credential, least privilege limits what it is
    worth

### Attached storage

- EBS = network-attached block devices used like a local disk; volume life is independent of the instance (stop, detach,
  attach elsewhere, data remains).
- Instance store = physically attached disk, erased the moment the instance stops. Confusing the two loses data
  permanently.
- Encryption by default for block storage: account-level setting, enabled per Region, not retroactive (existing volumes
  unchanged).
- Cannot encrypt an existing volume in place. Sequence: snapshot, copy the snapshot with encryption enabled, create a
  new volume from the encrypted copy, swap it in.
- Multi-Attach constraints:
  - provisioned-IOPS volume types only
  - single AZ
  - up to 16 instances
  - needs a cluster-aware filesystem
  - never the answer to shared storage across AZs (that is a file system, not a block device)
- `gp2`: IOPS scale at 3 per GB, so growing the volume raises its throughput ceiling. Short-term remedy only; `gp3`
  decouples IOPS from size and is usually better.
- Data Lifecycle Manager: scheduled snapshot and image creation, including cross-Region copies to several destinations.
  Covers block storage and machine images; does not cover relational databases (they have their own backups).
- Block storage has no cross-Region replication feature; you copy snapshots. A design describing continuous block-level
  cross-Region replication as a volume setting describes something that does not exist. Continuous cross-Region
  replication is a database feature or a job for the dedicated disaster-recovery service.

### Licensing and tenancy

- Dedicated Instances and Dedicated Hosts both give single-tenant hardware, but only a Dedicated Host exposes physical
  sockets and cores. That decides bring-your-own-license cases: per-socket and per-core licensing needs physical
  topology visibility. A Dedicated Instance gives isolation only.
- License Manager tracks entitlements and can block a launch that would breach them. Pair with Dedicated Hosts whenever
  licensing is a requirement.
- Nitro Enclaves: hardened isolated compute carved from a parent instance's own CPU and memory.
  - no persistent storage, no interactive access, no external network; only a local secure channel to the parent
  - purpose: process what the parent itself must never see (decrypted card data, private keys, a competitor's data in
    joint computation)
  - with KMS attestation, a key policy can release a key only to a specific verified enclave image, so even a
    full-access admin on the parent cannot get plaintext
  - pick when data must be processed excluding the OS, admins and the application alike; a Dedicated Host is not the
    answer (single tenancy isolates from other customers, not from yourself)

### When not to reach for EC2

- Bottleneck is not the thing being scaled: a bigger instance buys one step; if the constraint is read volume or shared
  state, vertical scaling postpones the problem about a quarter. Adding web servers in front of a saturated database
  moves the queue instead of draining it. Find the constrained resource first.
- Compute serving something not computed: an instance handing static files to a CDN pays a CPU for file reads. Serve
  from S3 and let the edge cache.
- "Centrally managed" in the requirement: a per-account proxy or appliance fleet is what centralized services replace;
  the word points away from per-account infrastructure.
- Rehosting carries the problem across: lift-and-shift to EC2 is fastest and often right, but wrong if the server is
  already overloaded (you moved the overload and paid for it).
- Workload cannot tolerate interruption: Spot is right for the interruptible half of a mixed workload, wrong for
  anything with an SLA, a live user session, or state nobody else holds.

## Auto Scaling: matching capacity to demand

- An Auto Scaling group (ASG) keeps a desired instance count, replaces failures, adds or removes capacity by rules.
  Converts a capacity guess into a policy.
- Use one even when not scaling: min = max = desired = same number still gives self-healing (dead instance replaced with
  no page). Instances outside a group need someone to notice. Self-healing is the point; scaling is the bonus.
- The group itself costs nothing; you pay for instances and monitoring. No budget argument against wrapping a static
  fleet in one.
- Auto Scaling does exactly and only what is configured. Production surprises are config mismatches: grace period
  shorter than bootstrap, a health check that is too deep, a minimum that pins you to one AZ.
- Prerequisite: dynamic scaling assumes a stateless, horizontally scalable workload. If an instance holds the only copy
  of something (session, upload in progress, hour-warmed cache), scaling destroys data. Move state out first.

### Choosing a scaling policy

| Policy                            | Use for                                                                                   | Limit or note                                                                                                  |
| --------------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Scheduled                         | Events with known date/time: launch, quarterly batch, shutting dev environments overnight | Guessing if traffic is truly unpredictable                                                                     |
| Predictive                        | Recurring cyclical patterns (daily, weekly) learned from history, provisions ahead        | Structurally cannot anticipate a one-off event it has never seen                                               |
| Dynamic (target tracking or step) | Reacts to a metric in real time                                                           | For CPU policies use average CPU across the group; keyed on maximum or sum is almost always a misconfiguration |

- Pairing: predictive for the pattern, scheduled for the dated event. Predictive for a one-off launch asks a model to
  forecast the unobserved.
- Attribute-based instance type selection: state needed vCPU and memory, group picks any matching type (including future
  types). Fewest later config changes, and widens the Spot pool, curing many launch failures. Naming specific types
  means revisiting config every generation.
- Launch configurations are legacy and support none of this; use launch templates.

### Lifecycle, health and termination

- Lifecycle hooks hold an instance in a wait state (starting or terminating) so your work runs first. `CONTINUE`
  proceeds normally; `ABANDON` also completes the action but marks it failed and skips remaining hooks. You can delay a
  termination, never cancel it.
- Health check grace period = how long the group ignores load balancer health checks after launch. Too short gives a
  launch-kill-relaunch loop (instance still bootstrapping, check fails, replaced, repeat); signature is instances
  cycling without ever serving traffic. The load balancer's own health-check timeout is a different setting (one check
  attempt); it does not extend the bootstrap window and tuning it will not fix slow boot.
- Warm pools: structural fix when bootstrap takes minutes. Group keeps pre-initialized stopped instances that enter
  service in seconds; slow work runs via a lifecycle hook while the instance sits in the pool. A scaling policy warm-up
  of zero seconds worsens incidents by sending traffic to unready instances.
- Gotcha for CPU-bound fleets: the group replaces instances the platform deems unresponsive; an instance at 100% CPU for
  minutes can look unresponsive and be terminated mid-job. Where sustained saturation is normal (batch rendering,
  simulation, compilation farms) review that default, and then you own noticing genuinely dead nodes.
- EC2 termination protection does not stop Auto Scaling; it blocks user-initiated termination only. To keep an unhealthy
  instance for forensics, suspend the `Terminate` process or move the instance to Standby.
- Scale-in protection stops the group removing an instance mid-job. Diagnostic signature: messages in a dead-letter
  queue with no matching application errors in logs (compute vanished under the work).
- Never patch in place inside a group: reboot fails the health check, group replaces the instance, patch lost. Bake a
  new image, update the launch template, run an instance refresh.

### Topology mistakes that are easy to miss

- Min and max both 1 means exactly one instance in one AZ regardless of subnets listed. Multi-AZ needs min above 1.
- A VPC described as having "a single public subnet" is a single AZ; an Application Load Balancer needs subnets in at
  least two AZs. Scan described topologies for this single point of failure hiding in the word "a".
- You can attach an existing load balancer or target group to a new ASG and register already-running instances. That
  introduces autoscaling to a running system with no downtime; a plan that deletes the load balancer or instances first
  accepts an outage.
- Keep load balancer health checks shallow. A check that queries the database turns a database slowdown into fleet-wide
  replacement (all fail together, group replaces all, new ones fail too). Use a shallow check for the load balancer and
  a separate deep check via Route 53 or a synthetic monitor for end-to-end monitoring.

### What Auto Scaling does not do

- Not a backup strategy: backups protect data and add nothing to uptime; a group maintains uptime and cannot recover a
  deleted table. Do not substitute one for the other.
- Not a multi-Region construct: throughput short inside a Region is fixed with capacity, caching or a read path in that
  Region. A second Region addresses geography, not local throughput, and adds cost and lag.
- Not networking: extra peering connections and NAT gateways do not address load or zone concentration. Capacity
  complaints are answered in the capacity layer.

## Lambda: compute without servers, and the ceilings that decide designs

- Upload a function; AWS runs it on a trigger, scales it automatically, bills per millisecond executed. No server to
  patch, size or keep running.
- "Serverless" means: you do not provision, scale or patch servers, and pay nothing when idle. The function runs in a
  managed execution environment AWS creates, reuses for a while, then discards. Cold starts, connection reuse, and
  globals surviving sometimes all follow from environments being created and destroyed outside your control.
- Fits bursty, short work: respond to an upload, transform a record, answer an API call, run every five minutes.
- Most common real-world Lambda: a scheduled rule invoking a function, replacing a small cron server (no instance, no
  patching, no "what if the cron box dies").
- One sizing control: you set memory; CPU scales proportionally (cannot be set independently). For CPU-bound work, more
  memory can lower the bill (finishes faster, billed on duration). The cheapest configuration is rarely the smallest.
- Most Lambda architecture decisions are decisions about whether you are near a hard ceiling.

### The limits that decide more designs than anything else

| Limit                       | Value                                                                                                                        | Note                                                              |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Max execution time          | 15 minutes (conventional function)                                                                                           | Hard ceiling; tuning does not change it. Check first, always      |
| Exception                   | 90 minutes on Lambda Managed Instances, async invocation or event source mapping, excluding Amazon MQ and DocumentDB (check) | Narrow carve-out; does not apply to synchronous invocation at all |
| Memory                      | up to 10,240 MB; roughly 6 vCPUs at the top                                                                                  | Memory rarely disqualifies Lambda; duration usually does          |
| Synchronous payload         | 6 MB in, 6 MB out                                                                                                            | Fix: put the object in S3, pass the key                           |
| Asynchronous payload        | 1 MB in                                                                                                                      | Same fix                                                          |
| Response streaming response | up to 200 MB (check)                                                                                                         | See below                                                         |

- Check duration in both directions: 5 minutes, 10 seconds, 600 seconds all fit; when stated duration fits, Lambda is
  often right because the alternative is managing infrastructure for seconds-long work.
- Function at the ceiling and still timing out: package the same code as a container image in a container registry and
  run it as a Fargate task triggered by the same event. The image lives in a container registry, not a versioned object
  store.
- Step Functions running functions in parallel does NOT extend any single function's runtime (parallelism is not
  duration). Fan-out helps when work is divisible; useless when one indivisible step takes two hours.
- Response streaming: function returns data progressively; response ceiling 200 MB (check) and the first byte reaches
  the client while the function still works. Fits large reports or proxying token-by-token model output. Works via
  function URLs and the AWS SDKs, not through a standard API Gateway REST integration (usually decides availability).
- Recursive-loop detection (safety net, not a design tool):
  - classic accident: function triggered by writes to a bucket it also writes to, or reading a queue it also publishes
    to; bills continuously and scales until account concurrency is exhausted
  - Lambda detects common cases via request metadata, stops the function after roughly 16 cycles, notifies the account
    owner
  - does not catch every loop, notably ones routed through a service it cannot trace
  - rule stands: never let output land in its own trigger without a prefix, suffix or flag that breaks the cycle

### Reserved versus provisioned concurrency

| Setting                 | Does                                                                                                      | Does not                           |
| ----------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| Reserved concurrency    | Guarantees that many concurrent executions AND caps the function at that number                           | Warm anything                      |
| Provisioned concurrency | Keeps execution environments initialized and warm; one purpose: remove cold-start latency; increases cost | Cap, protect, or warm-cap anything |

- Reserved uses:
  - protect a fragile downstream (e.g. an on-prem database that falls over above 50 connections) by making more
    connections impossible
  - fix a noisy neighbor: one function consuming most of the regional pool and starving another; reserve for the
    critical function (guarantees its floor, caps the greedy one)
- Tell them apart by the problem: throttling and starvation point to reserved; first-request latency points to
  provisioned.
- Neither is a pricing lever, neither enforces fairness between clients, neither explains why a function never ran
  (examine the trigger instead).
- Neither fixes too many database connections: the answer is a connection proxy. Provisioned keeps environments warm,
  and a warm environment holds its connection open, worsening the count.
- SnapStart: snapshots an initialized Java environment and restores on invocation; cuts cold starts at no additional
  charge (cheaper than provisioned concurrency where it applies). Works on published versions. Catch: anything
  generating a unique value during init breaks, because every restore replays the same snapshot (random seeds,
  connection IDs identical across environments). Move that work into the handler or use a runtime hook.

### Cold starts, and one piece of advice that is now obsolete

- Cold start = no warm environment; AWS creates one, loads code, runs initialization before the handler. Lightweight
  runtimes pay less; defer initialization work you can.
- Obsolete advice: attaching a function to a VPC used to add roughly 10 seconds of cold start (ENI per environment).
  That was re-architected and the penalty is gone. "Never put Lambda in a VPC because of cold starts" describes a
  product that no longer exists. Other reasons to think before attaching to a VPC remain (see Lambda inside a VPC).

### Versions, aliases and deployment

- Published version is immutable (code and environment variables). Only unpublished `$LATEST` is mutable.
- Alias = stable pointer clients call forever while you repoint it. Aliases carry weighted traffic shifting for canary
  deployments; versions cannot be weighted directly.
- Gradual rollouts: serverless application model plus the deployment service gives canary and linear traffic shifting,
  pre-traffic and post-traffic hooks, automatic rollback on a CloudWatch alarm.
- Layers are zip archives. A function packaged as a container image cannot use layers at all (mutually exclusive); a
  "layer built from a container image" does not exist.
- Function URLs: one HTTPS endpoint per function, no central routing, authorization layer or usage plan. Fine for a
  single webhook; poor as an API surface.

### Lambda inside a VPC

- A VPC-attached function has no public IP and cannot use an internet gateway. Outbound internet needs a NAT gateway;
  its elastic IP becomes the single source address (useful when a third party must allow-list you).
- Bigger surprise: attaching breaks default access to public AWS service endpoints. The function could reach the object
  store or queue service before; now it cannot until you add VPC endpoints or a NAT gateway. Nothing about the function
  changed, yet half the integrations stop.
- A function can be a target of an Application Load Balancer; it can never be a target of a Network Load Balancer.

### Connections, data and secrets

- Declare DB connections outside the handler so warm invocations reuse them. Limit: reuse is within one execution
  environment, not across concurrent ones; 1,000 concurrent executions = 1,000 connections. Pooling across them is what
  a connection proxy does.
- Connection proxy: credentials must be in a secrets manager (cannot read from a parameter store); fronts managed
  relational databases only, never on-premises.
- Environment variables are not a secret store: encrypted at rest but readable by anyone who can call the API returning
  function configuration (a far wider group than intended). Use a secrets manager, read at runtime.
- Async invocations: on-failure destinations can target a queue directly (review queue with no polling code); a
  dead-letter queue serves the same role for events that exhaust retries. A failed invocation should land where a human
  or process can find it, not vanish into a log.
- Logs go to CloudWatch with no configuration; distributed tracing is opt-in with one setting (fastest way to see why a
  function is slow when the slowness is in something it calls).

### When not to reach for Lambda

- Clock says no: any stated runtime over 15 minutes (first check, most commonly missed).
- No source code, or changing it is forbidden: moving logic into functions is a rewrite; a no-code-change requirement
  rules out the whole family.
- Least operational overhead is the priority and the proposal is decomposing a monolith: dozens of functions means new
  pipelines, new failure modes, distributed tracing instead of a stack trace. Possibly right long-term, never the
  low-effort option.
- A managed feature already does it (most common bad proposal in AWS, functions are the usual disguise):
  - scheduled function pruning container images reinvents registry lifecycle rules
  - function grepping logs reinvents metric filters
  - function copying snapshots between Regions reinvents the lifecycle manager
  - function auditing security group rules across accounts reinvents the firewall manager or access analyzer
  - before writing a function, ask whether you are rebuilding a named feature
- Durability required and no buffer: a function invoked directly from a bursty source will throttle, and throttled
  events are lost. If no data may be lost, put a queue or stream in front.
- Proposed fix unrelated to the bottleneck: a cache service the function does not call will not speed it up; an upload
  accelerator affects only uploads into a bucket; raising read capacity does nothing for a failing write path; adding
  memory to a function whose problem is waiting buys a more expensive wait.

## Containers: ECS, EKS, Fargate and the registry

- A container packages an app with its dependencies; value is packaging and isolation, not virtualization (shares the
  host kernel, so starts in milliseconds vs about a minute for a VM).
- An orchestrator decides where containers run, restarts dead ones, replaces them in deployments, wires networks and
  load balancers. Without one you have Docker plus shell scripts.
- Decision is a four-way grid: two orchestrators times two launch types.
  - ECS: AWS's own orchestrator; simpler, deeply integrated, no control plane to think about or pay for
  - EKS (Elastic Kubernetes Service): managed Kubernetes; more complex, more portable; right when Kubernetes itself is a
    requirement
  - Fargate launch type: containers with no servers to manage
  - EC2 launch type: containers on instances you own, patch and scale
- Containers sit between VMs and functions: Lambda stops at 15 minutes or long-lived processes; EC2 means you own the
  OS; containers on Fargate give minute-to-hour runtimes with no per-server maintenance.

### Choosing the platform

- ECS on Fargate is the default for "run containers with least operational complexity". Start there, move away only for
  a stated reason.
- Choose EKS when Kubernetes is needed: existing manifests in source control, dependency on the Kubernetes API, team
  already operating it, stated multi-cloud portability. Existing manifests make EKS the lowest-effort migration by far
  (ECS would mean rewriting each as a task definition).
- If Kubernetes is never mentioned and the ask is minimal complexity, EKS is wrong: per-cluster control-plane charge
  plus substantial operational knowledge.
- Self-managed Kubernetes on EC2 (running the control plane yourself) is never the answer to reducing overhead; it is
  what EKS exists to remove.
- EC2 launch type: when the requirement needs host control (specific networking, kernel parameters, GPU drivers,
  compliance agents on every node). Fargate abstracts the host, so any requirement about what runs on the host rules it
  out. A "team does not want to manage infrastructure" requirement rules the EC2 launch type out.
- ECS Anywhere and EKS Anywhere: consistent container platform across cloud and data center on your own hardware without
  migrating the workload.
- Lambda's ceiling is the problem but nobody wants to manage infrastructure: Fargate is the escape hatch.

### Fargate specifics

- Supports EFS volumes natively in the task definition. Does not support the high-performance Lustre file system; block
  volumes cannot be shared between tasks. Designs putting either under a Fargate task are unsupported combinations.
- Fargate Spot: roughly 70% discount for tasks tolerating a 2-minute interruption notice. Available for ECS, not for EKS
  on Fargate.
- Cost: Fargate bills per vCPU-second and GB-second of requested capacity, at a real premium over an equivalent EC2
  instance you run.
  - spiky or low-duty-cycle workloads: premium irrelevant (no paying for idle)
  - flat-out 24/7 fleet: premium is the dominant cost; EC2 launch type with reserved capacity underneath is materially
    cheaper
  - work out which you are before committing, not after the first full-month bill
- Trap: a cache inside a Fargate task is not a cache. Tasks are ephemeral; each warms its own copy and hit rate
  collapses exactly when traffic peaks and new tasks launch. Pre-generate artifacts and cache at the edge.

### ECS mechanics

- Service Auto Scaling scales the number of tasks. No Kubernetes-style cluster autoscaler for ECS; on Fargate there are
  no nodes to scale.
- Capacity providers scale the layer under the tasks (the piece people miss when a service "won't scale"). A provider
  ties a cluster to a capacity source: an Auto Scaling group, Fargate, or Fargate Spot. For the ASG case it enables
  managed scaling: ECS watches remaining room for new tasks and grows or shrinks the group to hold a target.
- Without a capacity provider you scale tasks against a fixed set of instances: the service tries to place a task, finds
  no host with enough CPU, and sits in `PENDING` forever while dashboards say scaling works.
- Capacity provider strategy spreads tasks across providers with weights and a base, e.g. "always keep two tasks on
  On-Demand, everything above on Spot" (resilience plus cost in one declaration, instead of two ASGs).
- Managed termination protection stops the group scaling in an instance still running tasks (the default failure mode
  when an ordinary ASG is wired to a container cluster).
- Beyond the cloud: three variants.
  - ECS Anywhere: control plane stays in AWS, external servers register as cluster capacity. Pick for existing on-prem
    servers that should appear in an AWS-managed cluster
  - EKS Anywhere: installs a complete self-contained Kubernetes cluster on your infrastructure that keeps running if the
    link to AWS drops. Pick for disconnected or intermittently connected sites
  - EKS Distro: just the open-source Kubernetes distribution AWS builds EKS from, no managed service
- Blue/green for ECS: driven by the deployment service, with a load balancer doing the target group swap.
- Register tasks directly with an Application Load Balancer target group to remove port contention (two copies of a
  service on a fixed port such as 8080 cannot share a host). Dynamic port mapping plus target-group registration fixes
  it; a good reason for a load balancer even with one task.
- Managed tags on a running task attach cost-allocation tags at task level (bill per running container). The EC2 launch
  type bills for instances, not tasks, so per-container chargeback and the EC2 launch type are incompatible
  requirements.
- `RunTask` API: what an external trigger calls to start one-off work; an event rule or function invoking `RunTask` is
  the standard way to hand a long job to Fargate when a function's ceiling is too low.
- `awsvpc` network mode: each task gets its own network interface, so security groups apply per task. With IAM roles for
  tasks this is the least-privilege container pattern. An instance role instead gives every container on the host the
  same permissions (almost never wanted).
- Logging is set per task via a log driver; the CloudWatch driver is the default worth using. Local files in an
  ephemeral task are deleted; logs must leave the task.
- Quota alarms: use CloudWatch usage metrics with the quota metric-math function to alarm on service quota utilization
  before an incident. Raising a quota is not autoscaling (a quota permits growth, does not provide it).
- Compute Optimizer now gives right-sizing recommendations for ECS services on Fargate, including task CPU and memory:
  the managed answer to finding over-provisioned tasks.

### AWS Batch, for when the unit of work is a job

- Managed batch computing: submit jobs to a queue with CPU and memory per job; Batch provisions compute (EC2, Spot or
  Fargate), runs them, scales back to nothing. Supports array jobs (same job across an index range) and job dependencies
  (run after another succeeds).
- Belongs in a design only for queues of jobs with scheduling semantics: many jobs, jobs contending for capacity, or
  dependencies between jobs.
- One job on a schedule does not need it: use a scheduled rule invoking a task or function (one job plus a cron
  expression means something simpler).

### The container registry

- Restrict pulls to your organization with a repository policy conditioned on the organization identifier (covers
  accounts added later with no edit). At larger scale, an org-level resource control policy does it for every current
  and future repository at once (governance chapter).
- Lifecycle rules expire images by age or count, including "keep only the N most recent untagged". A scheduled function
  that prunes images reinvents this.
- Scan on push emits an event when the scan completes, which automates quarantining a vulnerable tag. The event goes to
  the event bus (Amazon EventBridge), not directly to a queue; subscribing a queue without a rule in between skips a
  step.
- Periodic scanning delays detection; the basic scan is one-time, not continuous. For continuous scanning of images and
  worker nodes, use the dedicated inspection service (covers both).
- Built-in cross-Region replication, configured at registry level; no scripted image copies needed. Older material
  saying the registry cannot replicate is outdated (it could not for several years). Second-Region pull latency and
  availability are a configuration setting, not a pipeline.

### EKS node resilience

- Topology spread constraints keyed on Availability Zone distribute pods evenly across zones, so losing a node or a zone
  removes only a fraction of replicas. This is practical resilience for bursty stateless workloads.
- Rejected alternatives: fewer, larger nodes concentrate blast radius; deliberately underprovisioning leaves pods
  pending during bursts.

### When not to reach for containers

- Messaging layer would have to be rewritten: lift-and-shift of a Kafka-based app onto containers is fine; swapping
  Kafka for a different streaming service in that move is a rewrite of the messaging layer and violates a
  minimize-change requirement.
- Orchestrator heavier than the problem: one scheduled job needs no cluster, job queue or Kubernetes; use the smallest
  thing that runs it on a schedule.
- Per-task billing required but per-instance compute proposed: structurally incompatible, not a configuration matter.
