# Identity and security

Load this file when choosing or debugging IAM roles, cross-account or federated access, Organizations guardrails (SCP,
RCP, tag policies), KMS keys, secrets storage, security/detection services, directories or private CAs.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

## IAM: identities, roles and the assume-role pattern

### Vocabulary and decision order

- Principal = caller (person, app, AWS service). Action = `service:Operation`. Resource = named by ARN. Condition =
  narrows when a rule applies. Policy = JSON combining these four; attaches to identities or to resources.
- Decision order: (1) explicit deny wins, nothing overrides it; (2) else explicit allow grants; (3) else default deny.
- Default deny: a new identity can do nothing; "I did not deny it" never explains why something worked.

### Roles over users

- Think roles, not users. A role = permissions + trust policy (who may assume it). Nobody logs in as a role; a principal
  assumes it and gets temporary credentials that expire on their own.
- Why: long-lived keys sit in config files, laptops, build systems, public repos and work until noticed; temporary
  credentials expire regardless.
- Key prefixes: `AKIA` = long-lived IAM user key (almost always worth changing); `ASIA` = temporary session credential,
  needs a session token too.
- IAM changes propagate globally, not instantly; a policy edit that "didn't work" may need another minute.
- Keep IAM out of critical runtime paths; an app calling it per request ties its availability to IAM.
- Never commit credentials. Scanners find exposed AWS keys within minutes of a public push. Use a pre-commit scanner;
  assume anything committed once is compromised forever, even after force-push.

### Cross-account access

- The role lives in the account that owns the resource; its trust policy names the account needing access. Role in the
  wrong account or trust pointing the other way = standard mistake, design cannot work.
- Third parties: add an external ID to the trust policy; defeats the confused-deputy problem (vendor serving many
  customers tricked into using the wrong customer's role). Use whenever the other party is an external vendor.
- Handing a third party an access key is wrong in every case (long-lived, no expiry, hard to revoke).
- You assume a role, never a policy (policy has no trust relationship).
- Letting a junior assume a senior's role gives them ALL of that role's access, not a subset. For partial access, create
  a narrower role.

### Federation

- Federation lets existing identities (corporate directory, IdP, social login) get AWS credentials without parallel AWS
  users.
- In a federated sign-in there are no IAM users, so reasoning about "the IAM user's permissions" is meaningless. IdP
  authenticates, returns assertion/token, AWS exchanges it for temporary credentials against a role.

| Token source                                                        | Exchange call               |
| ------------------------------------------------------------------- | --------------------------- |
| SAML assertion (corporate directory)                                | SAML variant of assume-role |
| Public OIDC provider (social login, CI system, Kubernetes SA token) | `AssumeRoleWithWebIdentity` |

- `AssumeRoleWithWebIdentity` is the modern way to give a build pipeline AWS access with no stored key: pipeline
  presents its own short-lived identity token and receives AWS credentials.
- The IdP does not need to be reachable from your VPC: the user's browser does the redirect to the IdP and back;
  AWS-to-IdP network reachability is not part of the flow.
- Creating IAM users that mirror federated users duplicates identities and contradicts a single-identity-source
  requirement.
- CLI with MFA: tooling cannot prompt for a code itself; exchange long-term credentials for a temporary session carrying
  the MFA context first. Long-term access keys never carry MFA context.

### Policy evaluation and attributes

- Three tiers (same as above): explicit deny anywhere wins outright; else explicit allow from any applicable policy;
  else default deny. A deny in an SCP cannot be rescued by any IAM permission below it. Debug in that order.
- IAM is eventually consistent: a just-created role/policy/key may take seconds to be usable everywhere. Automation that
  creates a role and immediately assumes it fails intermittently. Add a retry; keep IAM writes out of critical paths
  that cannot tolerate seconds of lag.
- ABAC (attribute-based access control) uses tags on principal, resource or session tags, e.g. "manage resources tagged
  with your own team". It separates teams inside one account (org-level policies cannot, they act on accounts not
  principals within one).
- ABAC benefit: policy count does not grow with team count (20 teams = 1 tag-based policy vs 20 name-based).
- Policy variables differ by identity type: the IAM-user form does not resolve for identity-center principals, which
  need the principal-tag form. An unresolved variable silently matches nothing.
- Permissions boundary: caps what an identity can be granted, grants nothing itself. Used to safely delegate permission
  management (junior admin can create roles, none more powerful than the boundary). It bounds actions, not data; cannot
  express attribute-level filtering inside a table.
- Session policy: extra policy passed inline with the assume-role call. Session gets the intersection of the role's
  permissions and the session policy; never more than the role. Lasts exactly the session, nothing to clean up.
- Session policy use case: downscoping at moment of use. Multi-tenant app holds one role that can read the whole bucket;
  per request, assume with a session policy scoped to one customer's prefix so credentials physically cannot read other
  data. The role-based alternative is one role per tenant with unbounded role count.

| Policy type          | What it does                                                   |
| -------------------- | -------------------------------------------------------------- |
| Identity policy      | Grants                                                         |
| Resource policy      | Grants from the resource side; enables cross-account access    |
| Permissions boundary | Caps what an identity can ever be granted; attached in advance |
| Session policy       | Caps one session; passed at assume time                        |

- Condition keys that get swapped: the source-IP condition in an identity policy constrains where an API call comes
  from; the address range in a security group rule is a different key. Unrelated jobs.
- A launch template is convenience, not a constraint; nothing stops launching without it. Only constraints survive a
  determined engineer.
- Simulate policies before deploying with the policy simulator (evaluates a principal's effective permissions against
  specific actions/resources).

### Troubleshooting access denied

- Org-level controls are invisible from inside the account. Check in this order: org SCP, then any RCP, then the
  resource's own policy, then the permissions boundary, then the identity policy. People start at the bottom, which is
  slow.
- Access Analyzer finds resources reachable from outside a trust boundary; can use the whole organization as the zone of
  trust instead of one account (correct for org-wide questions). Pair it with an event rule for notification.

## Organizations: guardrails across many accounts

- Organizations groups accounts under one management account, with consolidated billing and policy types applying to
  accounts or OUs.
- Why multiple accounts: an account is the strongest isolation boundary (stronger than a VPC or any policy). Dev
  mistakes cannot touch prod, quotas do not contend, billing is attributable without tagging, blast radius of a
  compromised credential stops at the account edge. Cost: many accounts to configure consistently, which Organizations
  solves.
- Problem solved: at scale per-account config drifts and local admins can undo central decisions. Org policies cannot be
  removed by a member account; an IAM policy deployed per account can be deleted by any local admin.

### Service control policies

- SCP = maximum available permissions for principals in member accounts. Ceiling, not a grant.
- An SCP never grants. An allow statement in an SCP gives nobody new permission (identity policy must still grant).
  "Allow IAM actions only for administrators" does nothing alone; a new OU with an allow policy does not carve an
  exception to an inherited deny.
- Allow-list SCP requires removing `FullAWSAccess` (default, permits everything); until detached, a narrower allow list
  changes nothing. Conversely, removing it in a deny-list design blocks everything in that scope.
- SCPs never apply to the management account (good argument for keeping workloads out of it).
- Cannot be escaped from inside a member account, which is why it beats a per-account IAM policy.
- Cannot apply tags, cap spending or share resources; only allows/denies actions. Cannot separate teams sharing one
  account (acts on accounts, not principals); use attribute-based control.
- Consolidated-billing-only organizations have no SCPs; all features must be enabled.
- Verb in the requirement: prevent, disallow, block, remove the ability = preventive, policy. Detect, report, flag,
  assess compliance = config rules, which observe and record but stop nothing.

### Resource control policies

- SCP restricts your principals. RCP restricts other people's principals reaching your resources.
- "Prevent external principals from accessing our resources" = RCP. "Stop our developers doing X" = SCP.
- Canonical RCP: a deny with an organization-identifier condition, locking all current and future resources of a
  supported type to your org without editing resource policies across hundreds of accounts. Beats per-account
  bucket/repository policies (one resource each; someone must remember the next one).
- Like SCP: never grants; requires all features enabled; attaches at root, OU or account; does not affect the management
  account.
- Does not apply to service-linked roles or AWS-managed encryption keys.
- Covers a subset of services, among them object storage, container registries, the key service, secrets, queues,
  security tokens, logs and several developer tools.
- Effective permission = intersection of SCP, RCP, identity and resource policies; the action must survive all of them.
- To revoke access an external account holds over your resource: change the resource policy or apply an RCP. An SCP
  cannot (principal is not in your org).

### Tag policies and other controls

- A tag policy reports non-compliance; it does not enforce. Enforcement = an SCP denying resource creation when a
  required tag is absent.
- Control Tower: landing zone with guardrails, a log archive account and an audit account. Mandatory guardrails apply
  everywhere and cannot be scoped to one OU. Hand-building the same (policies, logging account, aggregators, conformance
  packs) works but fails any least-overhead requirement.
- Account Factory vends new accounts pre-enrolled with guardrails. Account Factory Customization applies a blueprint per
  new account (e.g. billing alarms) with no custom plumbing. Hand-rolled alternative (lifecycle event invoking a
  function deploying a template) works but is higher overhead.
- StackSets with service-managed permissions and automatic deployment push IaC to every account in an OU, including
  accounts created later; the mechanism for custom controls at scale.
- Scoping trap: applying a guardrail or policy at the root hits every account, not the subset intended.

### Account lifecycle and quotas

- Existing standalone account joins by invitation sent from the management account, accepted in the target account. The
  cross-account admin role is created automatically only in accounts Organizations created; an invited account needs
  that role built by hand.
- Consolidated billing comes automatically with Organizations; not a separate step.
- Service Quotas request templates store desired quota increases and auto-apply to every new account. Template must be
  created in `us-east-1`, from the management account, and applies only to accounts created after it exists, never
  retroactively.
- Service quotas limit how many of a resource you may create, never which services you may use; capacity mechanism, not
  access control.

## Encryption: KMS and secrets

- KMS creates/controls keys, enforces who may use them, logs every use. Most services integrate, making "encrypted at
  rest" a setting.
- Why KMS: key material never leaves the service (cannot be copied from a compromised instance); every use is
  policy-authorized and audited ("who decrypted this and when"); use is separately permissioned so you can revoke access
  to data without touching the data.
- Envelope encryption: data encrypted with a data key; the data key is encrypted by a key that never leaves KMS. Bulk
  encryption is local and fast; only the small data key goes to the service. Hence permissions come in pairs (generate
  data key to write, decrypt to read), grantable separately.

### Key types and what they imply

- AWS-managed keys: created and rotated for you, policy not editable. They cannot be shared across accounts, so
  cross-account snapshot/backup copy requires re-encryption with a customer-managed key first.
- Customer-managed keys: editable key policy, configurable rotation, full control. Only these qualify when the company
  must manage the key and rotate on its own schedule.
- Keys are Regional; material can never be exported. Ciphertext from one Region cannot be decrypted by a different key
  in another; that is what multi-Region keys are for. Separate single-Region keys either side of a boundary make data
  undecryptable (found at failover test).
- CloudHSM: single-tenant, FIPS 140-3 Level 3 validated hardware, you alone hold keys; required when a regulator demands
  exclusive custody. Check instance type when compliance is the point: `hsm2m.medium` carries 140-3 validation; legacy
  `hsm1.medium`'s 140-2 certificate is no longer current. Bridge to KMS = custom key store (keeps KMS integrations, key
  material in your own cluster).
- Imported key material (fourth option): for regulators requiring the key generated on the organization's own hardware
  and merely held by AWS. Import into a customer-managed key. Costs: AWS keeps no copy (lose material = key
  unrecoverable); no automatic rotation (you supply new material); optional expiry after which the key becomes unusable
  (control or dated outage).

### Rotation, grants and the ways access is actually granted

- Automatic rotation: new key material once a year, or a schedule you choose, down to 90 days. Key ID does not change;
  old ciphertext is NOT re-encrypted. KMS keeps every previous material version and decrypts old data transparently.
  Protects future data without migration; "rotate and re-encrypt everything" is two pieces of work.
- If existing data must be re-encrypted under new material (e.g. suspected compromise), rotation does not do it;
  re-encrypt yourself, typically with S3 Batch Operations or a snapshot copy.
- Rotation unavailable for: AWS-owned keys, imported material, keys in a custom key store, asymmetric keys. For
  asymmetric keys, create a new key and manage cutover (rotating a public key means redistributing it).
- Three access mechanisms that compose:
  - Key policy = root of authority. Unlike elsewhere in AWS, an IAM policy alone grants nothing unless the key policy
    delegates to the account's IAM. A user with `kms:*` in IAM can still be denied because the key was not told to trust
    IAM.
  - IAM policies grant to principals in an account the key policy delegated to.
  - Grants: temporary, programmatic, narrowly scoped permission one principal hands another (typically a service),
    retirable when work finishes. How AWS services get just-in-time key use for one operation without a permanent policy
    entry; the tool for temporary delegation that must expire.
- Cross-account use needs both halves: owning account's key policy allows the external principal AND the external
  account's IAM policy allows its user to call the key. One side only is the most common cross-account encryption
  failure, and the error reads like a key problem.
- Encryption context: key-value pairs bound into the operation; decryption fails unless the same context is supplied;
  appears in CloudTrail (integrity check and audit aid).
- Key deletion: scheduled, irreversible, waiting period 7 to 30 days; no immediate delete, no undo. To stop a key being
  used right now, disable it (reversible).

### Permissions and diagnostics

- Envelope-encrypted write needs permission to generate a data key; read needs decrypt. Permission to encrypt alone is
  not enough for a write.
- Diagnostic: reads succeed while writes fail on an encrypted resource = missing data-key-generation permission. The
  error message points at the resource, not the key.
- A key policy cannot prevent creation of an unencrypted resource (it never touches KMS). Prevention needs a policy on
  the resource-creating action.
- Public keys encrypt, private keys decrypt. Public key with the decryptor or private key with the encryptor =
  backwards.

### Secrets and parameters

- Secrets Manager: built-in automatic rotation, including managed rotation for supported databases (changes credential
  on both sides). Parameter Store: configuration and secure strings, cheaper, no rotation.
- Need automatic rotation: Parameter Store will not work. Config that never rotates: paying for the rotating store is
  waste.
- Neither stores or rotates SSH key pairs. Environment variables are not a secret store (anyone able to read a
  function's/task's configuration can read them).

## Security services and directories

- Services occupy different pipeline positions: generate signals, interpret, collect, turn into a human-actionable
  document. Questions differ: attack now (live telemetry), missing patch (inventory), personal data stored wrongly
  (content), evidence for auditor (reporting).
- GuardDuty watches behavior, Inspector watches inventory, Macie watches content, Security Hub collects, Detective
  explains, Audit Manager documents.
- None of these block anything; all are detective. Prevention = IAM, SCPs, security groups, firewalls. Proposing
  GuardDuty to stop an attack confuses noticing with stopping.
- GuardDuty: detects threats from logs and network telemetry (cryptomining, credential exfiltration, comms with
  known-bad hosts, unusual API calls from unusual places). Reads CloudTrail, VPC Flow Logs and DNS logs continuously
  without you enabling or paying for those logs separately (cheap to switch on). Detection logic exists and is
  maintained for you; writing your own is a permanent commitment.
- Security Hub: aggregates findings from other services and checks accounts against standards (CIS benchmarks, AWS
  Foundational Security Best Practices). It aggregates; scans nothing itself. With a delegated administrator account it
  is the single place for org posture (twelve accounts each with their own GuardDuty console is not a program).
- Inspector: continuous vulnerability scanning of instances, container images, functions against published vulnerability
  databases. Not patch compliance: Patch Manager (Systems Manager) applies and reports patches; Inspector finds
  vulnerabilities. Daily scanning plus regular patching needs both.
- Inspector scans the deployed function, not an archive in object storage. Function coverage is opt-out by tag, not
  opt-in (decide which to exclude). Inspects resources, not live traffic, so it is out for anything about what is
  happening on the wire now.
- Macie: discovers sensitive data in object storage. S3-only; discovers but never transforms. "Use Macie to anonymize"
  does not exist; masking/redaction belongs to a data-preparation service.
- Detective: after-the-fact investigation; behavior graph of what led to a finding (role assumed, from where, what it
  touched, what else happened). Investigation tool, not a posture dashboard: Security Hub says there are forty findings,
  Detective gives the story behind one. Use when the question moves from what is wrong to how it happened.
- Audit Manager: collects evidence mapped to a compliance framework and produces audit-ready reports.
- Four layers often substituted for each other: config rules evaluate settings; an aggregator centralizes results across
  accounts and Regions; conformance packs bundle rules against a framework; Audit Manager assembles evidence the auditor
  reads. A security findings aggregator belongs to none of these steps.

### Directories and end-user computing

| Service                  | Facts                                                                                                          |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| AWS Managed Microsoft AD | Real cloud directory; supports trusts, Group Policy, schema extensions                                         |
| AD Connector             | Proxies to existing on-premises directory, stores nothing; considerably cheaper than a trust where it suffices |
| Simple AD                | Samba-based subset; no MFA, trusts, schema extensions or Group Policy; needing any rules it out                |

- Where an external IdP already exists, a managed directory is usually unnecessary machinery.
- WorkSpaces: persistent virtual desktops; MFA is implemented with a RADIUS server, not a setting. Cross-Region HA uses
  connection aliases (one per Region, associated with a directory) plus a DNS failover record.
- AppStream: streams individual applications, not whole desktops. A full persistent desktop per user is expensive
  overkill for one app; streaming one app cannot replicate a full desktop.
- Private CA: issues internal certificates; unlike public managed certificates, they can be exported for use on
  instances and appliances. Share across accounts with the resource-sharing service (not by copying). One central CA
  beats one per account (like one prefix list beats fifty).
- A managed service's web dashboard is reached by a browser over HTTPS, not a shell on a bastion; for analysts, solve
  browser network reachability.

### Putting the pipeline together

- Use a delegated administrator account (usually a dedicated security account, not the management account, which should
  stay almost empty). GuardDuty, Inspector, Macie, Detective and Security Hub all support delegation; delegation
  auto-enrolls new accounts. Silently leaving the fifteenth account unmonitored is the most common mistake here.
- Decide what reacts: findings land in EventBridge, which turns detection into response (page a human, open a ticket,
  quarantine an instance by swapping its security group, revoke a session; e.g. GuardDuty finding above a severity
  threshold). Without that wiring findings pile up in a console nobody opens (a design flaw, not a staffing one).
- Evidence chain: AWS Config records resource state over time and evaluates rules; aggregator centralizes across
  accounts/Regions; conformance packs bundle rules against a named framework; Audit Manager assembles evidence mapped to
  the framework's controls. Four distinct steps. Security Hub sits outside the chain (collects security findings, not
  configuration evidence).
- AWS Artifact holds AWS's own certifications (SOC reports, ISO and PCI attestations). Auditor wants the platform's
  compliance = Artifact; wants yours = Audit Manager.
- Cost model: GuardDuty bills by volume of events analyzed; Inspector per resource scanned; Macie per bucket evaluated
  and per gigabyte inspected. So point Macie at specific buckets, and start with a sampling job rather than a full scan
  of a petabyte.
