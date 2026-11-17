# How to reason about AWS decisions (full detail)

Load when judging a design proposal, reviewing an architecture, or when `SKILL.md`'s short rules are not enough. This is
Part One of the source article, kept complete.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

## Core idea

Usually several designs work. The choice turns on what the organization optimizes for, which differs from what is
technically best. Two identical problems can have different right answers because one org needs cheap to run and the
other cheap to operate. Find the real priority first: it is rarely a formal requirement, but it appears in the brief, in
what the sponsor repeats, or in what failed last year. If it was never settled, asking is the highest-value kickoff
question.

## Priorities that recur

- **Lowest cost**: match the stated need and no further. Trap: over-delivering (a globally replicated database when 4
  hours of recovery is fine; a dedicated circuit for 50 Mbps). Over-engineering is wrong when money is the constraint.
- **Least operational overhead**: managed service, configuration over code, an existing feature over a built one. Any
  hand-written function that re-implements a native platform feature is a liability because someone owns it forever.
- **Least development effort**: fewest code changes, which differs from least running effort. Replatforming onto a
  managed service can cut ops while greatly raising development work. Different budgets, usually different owners.
- **Highest performance**: cost is explicitly not the constraint, so provisioned capacity, dedicated throughput and
  purpose-built engines win where they would lose on price.
- **Fastest failover**: it is about where the decision is made. In the request path: milliseconds. In DNS: no faster
  than health-check interval plus record TTL, so minutes. If seconds are needed, no DNS-based design delivers it.
- **Strongest security**: controls the constrained party cannot remove, preventive over detective (an organization-level
  guardrail beats a policy a local admin can delete). Prefer removing the credential over guarding it: a role assumed
  for 15 minutes beats a well-guarded access key.
- **Shortest time to migrate**: wall-clock including non-technical parts. Shipping hardware takes days, a dedicated
  circuit weeks to months; continuous replication over an existing link starts today and usually wins.
- **Highest availability**: survive loss of a component, a zone or a Region, and which one matters a lot. Error to
  avoid: treating a read-scaling mechanism as availability. Replicas needing manual promotion, and backups, are not HA.
- **Least ongoing toil**: recurring human effort, not initial build. Self-updating managed rule sets, vendor-maintained
  prefix lists, rate-based rules instead of curated address lists, tag-driven automation instead of per-account edits.
  Anything needing a human to keep a list current fails.

Cheap to run and cheap to operate often point to opposite designs: a self-managed Spot cluster is cheapest and the worst
choice for a three-person team already on call; a fully managed service is the obvious ops choice and may cost three
times as much.

## Prevent versus detect

- Words: remove the ability to, disallow, enforce, prevent. Control: preventive (service control policies, resource
  control policies, IAM policies, permission boundaries).
- Words: detect, identify, report, audit, notify. Control: detective (Config rules, Security Hub, Access Analyzer,
  GuardDuty).
- Offering a detective control where a preventive one was wanted is among the most common review mistakes, often made by
  people who know both services. The wording tells you which family is meant.

## Seven shapes of bad proposals

Learning the shapes lets you set aside two or three proposals before thinking hard about any.

### 1. The impossible combination

Two real services paired in a way the platform does not support. Ask whether you have ever seen them wired that way.

- AWS WAF attached directly to an EC2 instance or a Network Load Balancer. WAF attaches to CloudFront, Application Load
  Balancers, API Gateway, AppSync, Cognito user pools, App Runner and Verified Access, and nothing below HTTP.
- Exporting a public ACM certificate to your own servers. Not possible until June 2025, when exportable public
  certificates became a paid option; earlier-issued ones still cannot be exported. Private CA certificates can.
- A CloudFront Function calling a database. It runs in a restricted sub-millisecond environment with no network access;
  Lambda@Edge can make calls.
- Encrypting an existing EBS volume in place. Snapshot, copy the snapshot with encryption, create a new volume.
- A Lambda layer built from a container image. Layers are zip archives; container-image functions cannot use layers.
- Cross-Region replication of block volumes. Only snapshots copy across Regions.

### 2. Right service, wrong direction

- A queue publishing into a topic. SNS fans out to SQS, never the reverse.
- A cross-account role created in the account that needs access. It lives in the account that owns the resource, with a
  trust policy naming the account that needs access.
- Uploading the private key in CloudFront field-level encryption. Upload the public key; the private-key holder reads
  the fields.
- Inbound vs outbound Route 53 Resolver endpoints. Inbound lets on-premises resolve AWS names; outbound lets AWS resolve
  on-premises names. Reversing the arrow breaks the design.

### 3. The fabricated feature

A plausible capability that does not exist; harder to spot because only one service is involved.

- A managed policy named like "deny all AWS access" that you just attach.
- A cost-reporting tool with a "specialized template" for one analysis.
- A CloudFront setting for case-insensitive query strings.
- Automatic cross-Region failover that promotes an RDS read replica. Promotion is a manual API call or a script you
  write.
- A health check on a NAT gateway, or one elastic IP shared across several.
- A route table entry pointing at an S3 access point. Route tables route to endpoints; access points are reached by
  name.

### 4. Solving the wrong bottleneck

Real fix for something nobody complained about. Read latency is not helped by write capacity; scaling a web tier in
front of a saturated database moves the queue; more memory for a function idle-waiting on a network call makes it idle
faster at higher cost. Name the bottleneck in one sentence first and check every proposal against that sentence.

### 5. Hand-built version of a managed feature

A scheduled function, polling loop or script re-implementing a platform feature. It works but loses on operational
overhead because you own the code forever. Examples: pruning old images (ECR lifecycle policy), copying snapshots to
another Region (Data Lifecycle Manager cross-Region copy), parsing logs for over-provisioned instances (Compute
Optimizer).

### 6. Ignoring an explicit constraint

One sentence in the brief silently rules out half the designs (cannot modify the application, no long-term commitments,
traffic must not traverse the internet, no source code, device speaks only FTP). Find it first; it is usually phrased as
background in mid-paragraph. Drop every design that violates it without evaluating its merits.

### 7. The plausible look-alike service

Over 200 services, several with names that suggest the wrong job. Say what the service does in your own words before
accepting it; if you cannot, you are agreeing with a name.

| Looks like                         | Actually                                                                                      |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| OpsWorks (Chef, Puppet)            | Stacks reached end of life May 2024; patching, compliance, fleet ops are Systems Manager      |
| CodeGuru                           | Does not analyze permissions; least-privilege policy from activity is IAM Access Analyzer     |
| WorkSpaces Web                     | Not remote network access; remote users to private subnets is Client VPN                      |
| Monitron                           | Not edge ML; your own model at the edge is IoT Greengrass with a compiled model               |
| Data Pipeline                      | Not the data-movement answer; databases use DMS, files use DataSync                           |
| Detective                          | Not a posture dashboard; aggregated posture is Security Hub, Detective explores one finding   |
| Inspector                          | Not compliance reporting; patch compliance is Systems Manager Patch Manager                   |
| Macie                              | Not a general scanner; S3 only                                                                |
| SNS                                | Cannot run an SMS survey; two-way messaging is AWS End User Messaging (successor to Pinpoint) |
| Trusted Advisor                    | Reports; never enforces                                                                       |
| Price List API                     | Public list prices, not your spend                                                            |
| AWS Config                         | Evaluates and reports; a service control policy prevents                                      |
| QuickSight over a transactional DB | Not real-time dashboards; near-real-time operational dashboards are an OpenSearch stack       |

## Repeatable order for an unfamiliar problem

Do not read top to bottom forming opinions; the deciding sentence is rarely in the first paragraph and you will have
anchored by then.

1. Find what is optimized (cost, overhead, latency, recovery time, security). Ask if unstated.
2. Find the forbidding sentence (cannot modify the app, data must not leave the Region, no agent may be installed).
3. Name the bottleneck in one sentence of your own. If you cannot, you have not understood the problem.
4. Set aside on impossibility, not preference: discard only designs that cannot work or break the marked constraint. Do
   not rank yet. This halves the field and is faster and less error-prone than ranking while still reading.
5. Apply the priority to survivors; this is where cheap-to-run and cheap-to-operate diverge.
6. Check the numbers: a duration, size, recovery objective or throughput figure (15-minute ceiling, one-page limit, 400
   KB item). Half of hard problems turn on a skimmed number.

## Five discriminators when two designs both look right

Run in order.

1. **Managed vs self-built**: does one re-implement something AWS provides? (Firewall Manager vs hand-written plumbing;
   ECR lifecycle vs pruning job; Access Analyzer vs log parser.) Managed wins on overhead; self-built wins only with no
   managed equivalent.
2. **Preventive vs detective**: the wording says which.
3. **Direction and ownership**: who initiates, in whose account does the resource live? (inbound vs outbound resolver
   endpoints; endpoint vs endpoint service; cross-account role in target vs source account.) Half of plausible-but-wrong
   designs are the right parts wired backwards.
4. **A number**: Lambda 15 minutes vs a one-hour runtime; API payload 10 MB vs a large upload; a DNS TTL vs an RTO.
5. **Sufficiency**: over-delivers where cost is the constraint (global database for a 2-hour RPO), or under-delivers
   where availability is (nightly snapshots for a 30-second objective). Match the stated objective exactly.

## Count the problems

One mechanism per complaint. A brief with three complaints (cold starts, cost, injection) needs three mechanisms.

- Two mechanisms for one problem (a cache and a read replica both added for latency): at least one is unnecessary and is
  permanent cost and operational surface.
- A real, well-configured feature that nobody asked for still does not belong. Being right about a service is not the
  same as it being relevant. Say so out loud in a review.

## Resilience principles (Amazon Builders' Library)

### Control plane vs data plane

The control plane is the machinery for making changes (create, modify, delete, propagate). The data plane is the daily
work (route the packet, serve the object, read the volume). The control plane is more complex, so the data plane is
built simpler, with a higher availability goal and far more traffic. A running EC2 instance keeps serving even if
instance launching is impaired. Rule: never put a control-plane call on the recovery path. "Launch replacement instances
in the surviving zone" depends on the thing most likely to struggle during the failure; "the load balancer stops sending
traffic to the failed zone and running capacity absorbs it" depends only on the data plane. Keep change-making and
traffic-serving components apart and let the serving half run unattended.

### Static stability

The system keeps working when a dependency is impaired; it may stop getting updates but does not stop working. With 3
zones surviving the loss of 1, run each at about 66% of its load-tested capacity so two zones absorb the third. That is
about 50% more capacity than steady state needs, the price of not depending on a scaling event during an incident. Auto
Scaling replaces lost instances eventually; what serves traffic in the meantime must already exist. Likewise a running
standby database beats one you plan to create, and pre-warmed beats on-demand for anything in a recovery path.

### Timeouts, retries, thundering herd

- Pick timeouts from measured latency: decide the acceptable false-timeout rate (the example is about 0.1%) and set the
  value at that latency percentile. A guessed timeout is too long to protect or too short, manufacturing failures.
- Retry with capped exponential backoff, never immediately; immediate retries add load to the failing dependency.
- Add jitter (randomize the wait). Backoff alone synchronizes clients into regular waves. The same applies to cron jobs,
  polling and scheduled work where many clients share a tick.
- Retries are load amplification, so a retry policy is a capacity decision.

### Be suspicious of fallback

A fallback path runs rarely, so it is the least-tested code, first invoked under load during an incident, and often
shares the substrate that just failed (a cold, stale or equally impaired local cache or secondary store). Alternatives:

- Failover: switch wholesale to a standby that is already running and serving, so the path is exercised continuously.
- Let the caller handle the error: it has the context to know whether a degraded answer is acceptable.
- Hedge when latency matters more than cost: send the redundant request every time and take the first answer, so the
  redundant path cannot rot.

### Shuffle sharding

Ordinary sharding: 8 workers in 4 shards of 2, each customer on one shard; one abusive customer takes down a quarter of
the fleet. Shuffle sharding gives each customer a random pair of workers: 28 possible pairs for 8 workers and 2 per
customer, so two customers rarely share both. Published blast radius is about 3.6% against 25%. It grows with scale
because combinations grow combinatorially while the fleet grows linearly. It is probabilistic (partial overlap still
happens): it contains blast radius, it does not remove it. It buys isolation without dedicated infrastructure per
customer.

## Closing habit

Finish the sentence for any design: "This is the right choice because we are prioritizing X over Y, and here is what we
are giving up." AWS gives about four workable ways to do most things with different trade-offs; architecture is saying
out loud which trade-off you accept.
