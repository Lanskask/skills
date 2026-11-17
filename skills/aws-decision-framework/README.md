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

- `SKILL.md`: the questions to ask, the order of work, priority table, bad-proposal shapes, resilience rules.
- `references/tiebreakers.md`: the deciding axis for each pair of look-alike services.
- `references/limits.md`: the numbers that end designs.

## Source

Rules are paraphrased from John B Athappully,
[The AWS Decision Framework](https://medium.com/@john_b_athappully/the-aws-decision-framework-a41d29ca540b) (Medium, Nov
2026). Figures come from the article and are unverified.
