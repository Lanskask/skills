---
name: aws-decision-framework
description:
  Use for ANY question that picks between AWS services, features or designs, even a short one you could answer from
  memory: "Lambda or Fargate?", "SQS, SNS or EventBridge?", "DynamoDB or Aurora?", "ALB or NLB?", "is this enough
  (Config rule, replica, DNS failover)?", "which service does X?", or a review of an AWS design proposal, brief or
  exam-style scenario. Load it before answering: it carries the checks that catch impossible combinations, fabricated
  features, wrong-direction wiring, stale limits and detective-vs-preventive mix-ups. For designing a whole system,
  migration, DR plan or landing zone use `cloud-architect` instead; use this one for picking between options.
---

# AWS decision framework

Several AWS designs usually work. The job is to pick the one that fits what the organization optimizes for, and to say
what is given up. Source: John B Athappully, "The AWS Decision Framework" (paraphrased, see README).

## Ask the user first

Ask only what the request does not already say, in one short message:

1. What is optimized: lowest cost, least operational overhead, least development effort, highest performance, fastest
   failover, strongest security, shortest migration time, highest availability, or least ongoing toil?
2. Is there a one-line constraint that rules designs out (cannot modify the app, no source code, data must not leave the
   Region, no agent installable, no long-term commitment, traffic must not cross the internet)?
3. What is the actual complaint (the bottleneck), in one sentence?
4. Which numbers are fixed: recovery time, recovery point, runtime, payload size, throughput, budget?

If the priority is unstated, ask. If you must answer anyway, state the assumed priority in the first line.

## Order of work

1. **Priority.** Name the one thing being optimized (table below).
2. **Forbidding sentence.** Find the constraint that is written as background, and drop every design that breaks it
   without weighing its merits.
3. **Bottleneck.** Say what is wrong in one sentence before reading any proposal. Fixing a different bottleneck (more
   write capacity for a read-latency problem, more web servers for a saturated database) is a wrong answer.
4. **Eliminate on impossibility, never on preference.** Discard designs that cannot work or break the constraint. Do not
   rank yet. This usually halves the field.
5. **Apply the priority** to what survives.
6. **Check the numbers** against the survivor. A stated number is never decoration.

Then finish the sentence: "This is the right choice because we prioritize X over Y, and we give up Z."

## What each priority means

| Priority                 | Prefer                                                          | Trap                                                   |
| ------------------------ | --------------------------------------------------------------- | ------------------------------------------------------ |
| Lowest cost              | The design that meets the stated need and no more               | Over-delivering (global replication for a 4 h RTO)     |
| Least operational work   | Managed service, configuration over code, existing feature      | A hand-written function that redoes a platform feature |
| Least development work   | Fewest code changes, even if running it costs more              | Confusing it with the row above; they are two budgets  |
| Highest performance      | Provisioned and purpose-built capacity; cost is not a limit     | Picking the cheap option                               |
| Fastest failover         | A decision made in the request path (milliseconds)              | DNS failover: TTL plus health check, so minutes        |
| Strongest security       | Controls the constrained party cannot remove; no credentials    | Detective control where a preventive one was asked     |
| Shortest time to migrate | Replication over a link that already exists                     | Shipping hardware (days) or a new circuit (weeks)      |
| Highest availability     | Survive the loss of the unit that matters (component/AZ/Region) | Read replicas needing manual promotion, or backups     |
| Least ongoing toil       | Self-updating managed rules, tag-driven automation              | Any list a human must keep current                     |

Cheap to run and cheap to operate are different and often opposite (Spot cluster vs managed service).

## Prevent or detect

Words like prevent, disallow, enforce, remove the ability: use a preventive control (SCP, RCP, IAM policy, permission
boundary). Words like detect, report, audit, notify: use a detective one (Config, Security Hub, Access Analyzer,
GuardDuty). They are never interchangeable.

## When two designs both look right

Run these five in order; one almost always separates them.

1. **Managed vs self-built.** Does one re-implement a native feature (ECR lifecycle rules, Data Lifecycle Manager,
   Compute Optimizer, Access Analyzer)? Managed wins unless no managed equivalent exists.
2. **Prevent vs detect.** See above.
3. **Direction and ownership.** Who initiates, and in whose account does the resource live? SNS fans out to SQS, not the
   reverse; a cross-account role lives in the resource owner's account.
4. **A number.** Lambda 15 min, API Gateway 10 MB, DynamoDB item 400 KB, a DNS TTL vs an RTO. See
   `references/limits.md`.
5. **Sufficiency.** Over-delivers where cost rules, or under-delivers where availability rules? Match the stated
   objective exactly.

Also count problems: one mechanism per complaint. Two mechanisms for one problem means one is unnecessary. A true,
well-configured feature nobody asked for still does not belong in the design.

## Shapes of bad proposals

Check every proposal against these before ranking.

- **Impossible combination.** Two real services wired in a way AWS does not support (WAF on an EC2 instance or an NLB,
  exporting an ACM public certificate before the 2025 paid option, encrypting an EBS volume in place, layers on a
  container-image Lambda, cross-Region EBS volume replication). Ask whether you have seen it wired that way.
- **Right service, wrong direction.** Queue into topic, role created in the wrong account, private key uploaded where
  the public key goes, inbound vs outbound Resolver endpoint swapped.
- **Fabricated feature.** A plausible setting that does not exist (a "deny all" managed policy, automatic cross-Region
  RDS replica promotion, a NAT gateway health check, a route to an S3 access point).
- **Wrong bottleneck.** See step 3.
- **Hand-built managed feature.** A scheduled function doing what the platform already ships.
- **Ignored constraint.** See step 2.
- **Look-alike service.** The name suggests a job the service does not do. Say what it does in your own words before
  accepting it (Config reports, SCP prevents; Trusted Advisor reports, never enforces; Macie is S3 only; Security Hub
  aggregates, Detective investigates one finding; Price List API is list prices, not your spend).

## Resilience rules

- Keep control-plane calls (launching, changing resources) off the recovery path; depend on the data plane.
- Statically stable: capacity must already exist. Across 3 AZs surviving 1 means about 66% load each, so about 50% extra
  capacity.
- Timeouts from measured latency, retries with capped exponential backoff plus jitter. Retries add load.
- Distrust fallback paths (rarely run, often on the same failed substrate). Prefer failover to a running standby, let
  the caller handle the error, or hedge requests.
- Shuffle sharding limits one abusive tenant's blast radius without per-tenant infrastructure.

## References

The sections above are the short form. Load only the file the question needs; each one keeps every rule from its part of
the source article.

| File                                       | Load for                                                                                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| `references/reasoning.md`                  | Reviewing a proposal: full priority list, all seven bad shapes, look-alike table, resilience                                          |
| `references/tiebreakers.md`                | Which of two look-alike services: the deciding axis per pair                                                                          |
| `references/limits.md`                     | Numbers that end designs: runtime, payload, throughput, failover and recovery ladders                                                 |
| `references/compute.md`                    | EC2, Auto Scaling, Lambda, ECS/EKS/Fargate/Batch, container registry                                                                  |
| `references/storage-and-data.md`           | S3, EFS/FSx, Storage Gateway/DataSync/Snow, RDS/Aurora, DynamoDB, analytics, streaming                                                |
| `references/networking-edge.md`            | VPC, peering/Transit Gateway/PrivateLink, Direct Connect/VPN, Route 53, load balancers, CloudFront, WAF/Shield, API Gateway           |
| `references/identity-security.md`          | IAM, Organizations (SCP/RCP), KMS and secrets, security services, directories                                                         |
| `references/operations-and-integration.md` | CloudFormation, Systems Manager, observability, CI/CD, migration and DR, cost, SQS/SNS/EventBridge/Step Functions, platforms, IoT, ML |
| `references/lesser-known.md`               | Narrow-job services (S3 Object Lambda, Lake Formation, AppFlow, AppConfig and others)                                                 |

Numbers and service facts come from one article written in Nov 2026. Treat them as unverified and check current AWS
documentation before a decision that depends on a specific figure.
