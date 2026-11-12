---
name: openapi-optimizer
description: >-
  Deterministic playbook for optimizing large OpenAPI / Swagger specifications
  for LLMs and AI coding agents. Use when dealing with large API specs (>2,000 lines, >20k tokens)
  to reduce token consumption by 60% to 95% using modular splitting, type compilation,
  and high-density markdown cheatsheets.
---

# OpenAPI Optimizer Skill

This skill provides a battle-tested, deterministic runbook to compress, split, and optimize large OpenAPI/Swagger specifications for AI agents and LLMs.

---

## When to Activate

Activate this skill when:
- The user provides an OpenAPI / Swagger spec that is too large (>20,000 tokens / >2,000 lines).
- An LLM needs to make API calls or generate client SDKs without burning massive token budgets.
- An agent needs to navigate an API without loading the entire monolithic document into context.

---

## The Optimization Playbook

### 1. Measure Baseline Token Economy
Use Python and `tiktoken` (or character counts) to establish the baseline before touching files:
```bash
uv run --with pyyaml --with tiktoken python3 -c "
import json, yaml, tiktoken
enc = tiktoken.get_encoding('cl100k_base')
raw = open('openapi.json').read()
d = json.loads(raw)
yaml_str = yaml.dump(d, sort_keys=False)
print('JSON Tokens:', len(enc.encode(raw)))
print('YAML Tokens:', len(enc.encode(yaml_str)))
"
```
*(Note: Converting JSON to YAML typically only saves 10-15% of tokens. It is rarely sufficient on its own.)*

---

### 2. Strategy A: Multi-File Modular Split (Best for AI Coding Agents)
Coding agents with file-reading tools do NOT need the whole spec in one file. Split it so the agent can read only the specific route it needs:
```bash
npx -y @redocly/cli split openapi.yaml --outDir spec
```
**Result:**
- Root `spec/openapi.yaml`: Contains only tags, servers, and relative `$ref` route pointers (~250-400 tokens).
- Route files `spec/paths/<route>.yaml`: ~1,000-3,000 tokens each.
- The agent reads the root index, finds the relevant endpoint, and reads **only** that specific file.

---

### 3. Strategy B: Compile to Native Language Types (Best for Code Generation)
Instead of forcing the LLM to parse verbose JSON Schema syntax, compile the schemas to native typed models:

**For Python (Dataclasses / Pydantic):**
```bash
uvx --from datamodel-code-generator datamodel-codegen \
  --input openapi.yaml \
  --output models.py \
  --output-model-type dataclasses.dataclass
```
*(Typical reduction: **90% token savings** over raw OpenAPI JSON).*

**For TypeScript:**
```bash
npx -y openapi-typescript openapi.yaml -o types.ts
```

---

### 4. Strategy C: High-Density Markdown Cheatsheet (Best for Prompt Context)
For 95% of tasks, an LLM only needs:
1. HTTP Method + Path
2. Parameter names, types, and whether they are required
3. Return schema name

Generate an `API_CHEATSHEET.md` using a script that groups shared query parameters into a single reusable table and outputs a compact Markdown directory.
*(Typical reduction: **95%+ token savings**, e.g., 65k tokens -> 2.5k tokens).*

---

### 5. Strategy D: Deduplicate Parameters & Strip Doc Bloat
In monolithic specs, parameters are frequently repeated inline across multiple endpoints.
1. Extract duplicate parameters to `components.parameters.<paramName>`.
2. Replace inline definitions with `{"$ref": "#/components/parameters/<paramName>"}`.
3. Truncate long descriptions to their first sentence and remove redundant `example` blocks.
4. Validate the resulting compact spec:
   ```bash
   npx -y @redocly/cli lint openapi.compact.yaml
   ```
*(Typical reduction: **60-70% token savings** while remaining a 100% valid standalone OpenAPI 3.x document).*
