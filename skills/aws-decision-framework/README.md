# aws-decision-framework

A skill for choosing between AWS services and judging AWS design proposals. It makes the model find the priority first
(cost, operations, failover speed, security), then drop designs on impossibility or a forbidding constraint, then rank
what is left and check the numbers.

## Use

Ask a choice question in Claude Code, for example "Lambda or Fargate for a 5-minute batch job?" or "SQS, SNS or
EventBridge for order events?". It needs no scripts or dependencies.

Use `cloud-architect` (a separate skill, not in this repo) for whole-system design, migration plans and DR strategy. Use
this skill to pick between options.

## Files

- `SKILL.md`: the short form (questions to ask, order of work, priority table, bad-proposal shapes, resilience rules)
  and an index of the reference files.
- `references/`: the whole source article, split by topic and loaded on demand: `reasoning.md` (Part One), the five
  service-area files `compute.md`, `storage-and-data.md`, `networking-edge.md`, `identity-security.md` and
  `operations-and-integration.md` (Part Two), and `tiebreakers.md`, `limits.md` and `lesser-known.md` (Part Three).

## Source

Rules are paraphrased from John B Athappully,
[The AWS Decision Framework](https://medium.com/@john_b_athappully/the-aws-decision-framework-a41d29ca540b) (Medium, Nov
2026). Figures come from the article and are unverified.
