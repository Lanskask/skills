# Networking and edge

Load this file when the question is about VPC design, connecting VPCs or on-premises networks, DNS, load balancers,
CloudFront, edge security (WAF, Shield, firewalls) or API Gateway.

Facts are as reported by the source article (Nov 2026) and unverified; confirm in AWS documentation before relying on a
figure.

## VPC fundamentals

- VPC = private network in AWS: address range you choose, split into subnets, with routing and firewalling you control.
- Scope facts:
  - A VPC belongs to one Region in one account.
  - A subnet belongs to one VPC and one AZ and never spans zones. "Across 3 AZs" means at least 3 subnets.
  - A security group belongs to one VPC.
  - You choose the address ranges, so two VPCs can collide on the same range. This causes connectivity problems later.
- Public vs private subnet is purely routing: public = route table has a route to an internet gateway, private = it does
  not. There is no checkbox.

### Getting out, and letting things in

- Internet gateway: two-way traffic for resources with public addresses.
- NAT gateway: private resources reach out, inbound refused. Use for app servers that download packages but must not be
  reachable.
- IPv6 equivalent is an egress-only internet gateway. A NAT gateway does not do IPv6 (common wrong substitution).
- Security groups and route tables hold IPv4 and IPv6 entries separately. A rule for one does nothing for the other, so
  connectivity works for half the clients.
- A NAT gateway lives in one AZ. One shared gateway makes that AZ a dependency for all others. Resilient pattern: one
  per AZ, each private subnet routed to the one beside it.
- An elastic IP cannot be shared across several NAT gateways. NAT gateways have no health check of their own.
- NAT gateway cost: per hour plus per GB processed. Private fleets pulling terabytes from S3 via NAT pay processing on
  every byte.
- Fix: a gateway endpoint (free) removes that traffic from the NAT path. One of the highest-value free cost fixes.
- Not the answer:
  - Moving instances to public subnets to avoid NAT charges destroys the security posture.
  - NAT instances are cheaper per hour but bring back patching, scaling and loss of managed HA. They move the wrong way
    for "reduce operational overhead".

### Security groups versus network ACLs

| Aspect          | Security group                                      | Network ACL                               |
| --------------- | --------------------------------------------------- | ----------------------------------------- |
| State           | Stateful (return traffic automatic)                 | Stateless (return traffic needs own rule) |
| Ephemeral ports | Never appear in rules                               | Appear in rules                           |
| Default         | Inbound denied, all outbound allowed unless changed | n/a in article                            |

- An ephemeral-port rule in a security group means ACL thinking applied to the wrong object.
- Security groups can reference other security groups ("web tier may reach DB tier") without hard-coded addresses. Works
  within a VPC or across a same-Region peering connection. Does not span an organization and is not a global naming
  system.
- Practice: one security group per tier per service, not one permissive group everywhere. Makes "who can reach the DB"
  readable.
- Security groups cannot express geography and cannot log denials. Geography points to a web firewall (WAF). Denial
  logging points to flow logs or a network firewall.
- They are layer 3/4 only: a port rule cannot express a protocol on another port; blocking port 80 says nothing
  about 443.
- Managed prefix lists hold AWS-maintained address sets, including one for CloudFront origin-facing ranges. Reference it
  in the load balancer's security group to lock an origin to CloudFront without maintaining address lists.
- Do not create a prefix list per account (recreates the sync problem). Share one from a central account.

### Endpoints: reaching AWS services privately

| Aspect            | Gateway endpoint                                            | Interface endpoint                                                      |
| ----------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| Services          | S3 and DynamoDB only                                        | Most services                                                           |
| Cost              | Free                                                        | Per hour and per GB                                                     |
| Mechanism         | Route table entry (route-based)                             | ENI with private IP in your subnet, ordinary routing + private DNS      |
| From on-premises  | No (only from inside the VPC; VPN/DX traffic cannot use it) | Yes                                                                     |
| Route table entry | Yes                                                         | None. A design routing to an interface endpoint has the mechanism wrong |

- Pattern when both in-VPC resources and on-premises users need private S3 access: gateway endpoint for VPC traffic
  (free), interface endpoint for on-premises traffic (only one that works from there).

### Address planning and immutability

- Subnet CIDR ranges are immutable; cannot be resized. Exhausted subnet remedy: create a new one and migrate. Address
  planning is one of the few genuinely hard-to-undo decisions.
- IPAM: plans, allocates, tracks and audits address space across accounts and Regions with pools and automatic
  allocation. Signal: running out of or colliding on address space at scale. Organizational problem: with 40 teams
  creating VPCs, a spreadsheet stops working at about the 10th VPC.
- DHCP option sets carry DNS and NTP servers, so pointing instances at an on-premises time source is a VPC-level
  setting.
- Pointing DNS at a hard-coded resolver instead of the AWS-provided resolver breaks private hosted zone resolution
  (private names stop resolving; rarely the first thing checked).
- Reachability Analyzer: "can this packet get there", static configuration analysis, sends no traffic.
- Network Access Analyzer: finds unintended access paths.
- Both are audit/troubleshooting tools, not runtime controls.

## Connecting VPCs: peering, Transit Gateway and PrivateLink

- Three mechanisms for three problem shapes. A wrong choice works at small scale and collapses at large scale (arrives
  ~18 months later).

### Peering

- Direct one-to-one link between two VPCs; private addresses reach each other. No hourly charge, nothing to operate,
  same latency as within a VPC. Use case: two VPCs that need to talk.
- Hard limits:
  - Not transitive (A-B and B-C does not give A-C). No setting for it.
  - Cannot use the peer's NAT gateway, internet gateway or VPN (edge-to-edge routing unsupported).
  - Overlapping CIDRs make it impossible. Test containment, not only equality (a /16 containing the other side's /24
    overlaps).
- Scale: each pair needs a connection plus route entries on both sides. Quadratic: 10 VPCs = 45 connections; 100 VPCs
  full mesh = 4,950. Manual route table maintenance causes mistakes.
- Cost: data transferred across a peering connection is charged. Chatty cross-VPC workloads can get costly enough to
  change the architecture.

### Transit Gateway

- Regional hub. VPCs, VPN connections and dedicated circuits each form an attachment; the gateway routes between them
  with its own route tables.
- Solves: many VPCs (e.g. 30) plus a data center over VPN, all needing shared services. Peering means hundreds of
  connections and touching every route table per new VPC. Fails through accumulated human error, not a technical limit.
- Hub model: each VPC = one attachment + one route to the gateway. The 31st VPC is one attachment and one route.
  Transitive by design, so the data center reaches all VPCs via a single VPN attachment.
- Segmentation: TGW route tables express "prod VPCs reach shared services but not each other", "sandbox VPCs reach the
  egress VPC only". Otherwise this is enforced only by not creating certain peerings (memory-based control).
- Most misunderstood: the VPC route table just points at the TGW. All reach decisions live in the TGW route tables.
  Editing the VPC route table to segment is editing the wrong object.
- Cost: per attachment-hour and per GB.
  - For a handful of fixed point-to-point links where cost decides, peering (no hourly charge) wins.
  - An attachment per short-lived environment means churn and quota pressure for no benefit.
  - The hub earns its keep through scale and manageability, not cost.
- Cross-account sharing: enable auto-accept, otherwise each recreated environment waits for someone in the owning
  account to accept.
- Sharing uses AWS RAM (Resource Access Manager), the general mechanism to lend resources to other accounts in the org:
  transit gateways, subnets, Route 53 resolver rules, license configurations, Private CA. Answer to "networking account
  owns, app accounts use"; alternative is one of everything per account.
- Transit Gateway Connect: attachment type for software appliances (SD-WAN, virtual routers).
  - Runs GRE over an existing VPC or Direct Connect attachment and speaks BGP; dynamic routing with much higher
    throughput than an IPsec tunnel.
  - Use when a third-party SD-WAN/virtual router needs native dynamic routing instead of a static tunnel.
  - It rides on top of an existing attachment; not a way to connect something with no path yet.
- Multicast: transit gateways support multicast domains. The only managed answer when a legacy app needs it (market data
  feeds, some industrial protocols). A VPC alone does not route multicast.

### PrivateLink

- Exposes one service, one direction, without joining networks. Provider puts a load balancer in front and publishes an
  endpoint service. Consumer creates an endpoint in its own VPC (ENI with private IP). Traffic goes consumer to service
  only.
- Peering and VPN join whole address ranges (too much access for "customers call our API privately"). PrivateLink
  changes no routes and needs no address agreement.
- It is the only one of the three that works with overlapping CIDRs (nothing is routed). Matters when the other party is
  a customer or vendor.
- The word "one-way" in a requirement signals PrivateLink.
- An endpoint service must be fronted by a Network Load Balancer or Gateway Load Balancer, never an ALB directly. For
  layer-7 routing behind it: NLB in front, ALB registered as its target.
- Direction trap: creating an endpoint service makes you the provider; the consumer creates an endpoint. Backwards
  inverts the design.
- Interface endpoints to AWS services are the same technology (AWS is the provider).

### Newer alternatives worth knowing

- Cloud WAN: managed global network from a central policy document with segments; replaces a hand-built mesh of transit
  gateways and peering across Regions. When a requirement wants dedicated bandwidth, multiple Regions and central
  management together: Cloud WAN with dedicated-connection attachments.
- VPC Lattice: service-to-service connection and authorization across VPCs and accounts at application layer; avoids
  peering and overlapping-CIDR problems. Use when the unit is "service calls service", not "network reaches network".
- Resource Access Manager subnet sharing: a second account launches resources directly in a central VPC and inherits its
  connectivity; no peering, no duplicate networking.
  - Cannot be shared: VPN connection, virtual private gateway, NAT gateway. Share the subnets and connectivity comes
    with them.
- Organization-level policies are guardrails: they restrict, grant nothing, share nothing. A policy is never the
  mechanism for one account to gain access to another's resource.

## Hybrid connectivity: Direct Connect and VPN

- Site-to-Site VPN: encrypted tunnel over the public internet. Provisions in hours, low cost, subject to internet
  conditions. Cannot promise consistent or predictable performance, so it will not meet a contractual latency figure at
  any price.
- Direct Connect (DX): dedicated physical circuit to an AWS location, usually via a partner data center. Consistent
  latency, higher throughput, no internet in path. Weeks to months to provision (cable must be run), so it cannot be the
  answer to anything needed this quarter.
- Over-specification: 50 Mbps of traffic does not justify a dedicated circuit; VPN is proportionate and costs two orders
  of magnitude less.
- Common end state: dedicated connection plus VPN as backup. A fraction of the cost of a second circuit, removes the
  single point of failure; on backup days bandwidth is degraded and latency higher. Acceptable or not is a business
  question; ask it out loud.
- DX economics:
  - Bills a port-hour fee plus per-GB data transfer out, substantially cheaper than internet egress (often less than
    half).
  - Heavy egress can pay for the circuit by itself; latency is a bonus.
  - Mostly-inbound workloads see no savings (data in is free either way).
  - Do this arithmetic first.
- Hosted connections: sub-gigabit slice through a DX partner (50, 100, 200 Mbps and upward) instead of a whole 1, 10 or
  100 Gbps port. Provisioned in days, not months (partner already has the link). Often right for predictable latency
  without big bandwidth; commonly overlooked.

### Virtual interfaces and gateways

- A virtual interface (VIF) is the logical connection over the physical circuit. Three kinds:

| VIF type | Reaches                                             |
| -------- | --------------------------------------------------- |
| Private  | A VPC, through a virtual private gateway            |
| Transit  | A transit gateway, through a Direct Connect gateway |
| Public   | Public AWS endpoints                                |

- Know cold: a private VIF cannot reach a transit gateway; a Direct Connect gateway cannot route between two transit
  gateways (needs transit gateway peering).
- Transit VIF used to require a connection of 1 Gbps or more. Article says that restriction is gone: any dedicated or
  hosted connection at any speed. Designs rejected on that ground are worth revisiting; the old figure is still widely
  repeated, including in current material (check).
- One Direct Connect gateway reaches many Regions. A separate circuit per Region is the expensive mistake.
- MACsec: link-layer encryption on dedicated connections at higher port speeds only; not on 1 Gbps links, not on hosted
  connections. DX now offers 1, 10, 100 and 400 Gbps ports over single-mode fiber; check the current support matrix for
  your speed. It is encryption, not routing; never fixes a reachability problem.
- SiteLink:
  - Enable on two private or transit VIFs at different DX locations; traffic between your own sites flows over the AWS
    global backbone without entering a VPC.
  - Example: London to Singapore office traffic uses the AWS network instead of a carrier circuit. Billed per hour plus
    data transferred.
  - Answers branch-to-branch or DC-to-DC connectivity where DX already exists; alternatives are an expensive private WAN
    or a VPN mesh.
  - Recognize it by the absence of a VPC in the requirement: no AWS destination means no ordinary VIF helps.
- DX resilience model:

| Level   | Design                                                        |
| ------- | ------------------------------------------------------------- |
| None    | Single connection                                             |
| High    | Two connections at two different DX locations                 |
| Maximum | Two connections at each of two locations, on separate devices |

- A second connection at the same location protects against device failure, not location failure.
- Cheap answer: VPN as backup to a single circuit; lower bandwidth, higher latency when active; usual choice when cost
  is binding.
- Transit VPC (self-run routing appliances on instances) was replaced by managed gateways. Still in older designs;
  reintroduces patching, scaling and availability work.

### Two constraints that eliminate proposals instantly

- Encryption is not privacy of path. TLS protects bytes but traffic still crosses the public internet. "Must not
  traverse the internet" requires a private path.
- Site-to-Site VPN carrying IPv6 requires a transit gateway. A virtual private gateway does not support IPv6 for
  Site-to-Site VPN, so every VGW option fails once IPv6 appears.
- A VPC can have only one virtual private gateway. VPN redundancy: two VPN connections to two customer gateways, each
  with two tunnels (four tunnels, one gateway). A second VGW for the same VPC is impossible.
- Client VPN: individual remote users reaching private subnets (Site-to-Site joins networks). Billed per
  subnet-association hour and per client-connection hour; an endpoint per environment inflates the bill.

## Route 53 and DNS

- Managed DNS plus health checking and routing policies. DNS is the earliest point to steer a user (nearest Region, away
  from failure, onto a new version) and the bluntest.
- Commitment: plain records are portable (move in an afternoon). Alias records and geographic routing policies are Route
  53 features with no direct equivalent elsewhere, so more logic in DNS means more provider dependency. Usually fine,
  but a trade.

### The routing policies

| Policy       | Behavior                                                      |
| ------------ | ------------------------------------------------------------- |
| Simple       | Returns a record                                              |
| Weighted     | Splits traffic by proportion                                  |
| Latency      | Each user to the Region with lowest measured latency for them |
| Geolocation  | Decides by where the user is                                  |
| Geoproximity | Biases by distance with adjustable bias                       |
| Failover     | All to primary, switch to secondary on health-check failure   |
| Multivalue   | Returns several healthy records                               |

- Latency-based and geolocation are not interchangeable. Goal "minimise latency" = latency-based (measured performance).
  Geolocation correlates with latency but does not measure it; breaks where topology is unusual.
- Failover always prefers the same primary regardless of user location, so it never answers a proximity requirement.
- Latency and weighted records can be combined by nesting; claiming they cannot is wrong.

### Where DNS stops being enough

- Root cause: DNS answers "what address is this name" and lets anyone cache the answer. All limits below follow from
  that.
- Caching cannot keep a client anywhere. Weighted routing will not pin a user to a version (resolver caching, clients
  re-resolve on their own schedule). Pinning is a load balancer job via target group stickiness. Canary via weighted DNS
  shows some users both versions at random.
- Caching sets a floor on failover time: TTL plus health-check interval plus misbehaving resolvers. An RTO shorter than
  the TTL cannot be met by DNS. Lowering TTL to a few seconds multiplies query volume and still loses to an
  in-request-path mechanism. When seconds matter use CloudFront origin groups, Global Accelerator or a proxy.
- Steering is not blocking. Geolocation routing does not stop access; the resource stays reachable by address and a
  different resolver bypasses it. Treat it as performance/convenience, never a control. Geographic restriction belongs
  in WAF (inspects the request, not the lookup).
- A CNAME is invalid at a zone apex (DNS rule: apex holds SOA and NS; CNAME cannot coexist). Answer: alias record (Route
  53-specific; works at apex, resolves to AWS resources, free to query). It also makes leaving Route 53 harder: an apex
  pointing at a load balancer must be redesigned, not exported.
- A record can only point at something that exists. DNS moves traffic, does not build infrastructure; a DR plan whose
  second Region is just a DNS record fails over to nothing.

### Health checks and resolvers

- An alias record needs Evaluate Target Health enabled to react to target state. A weighted record needs its own health
  check. Omitting them routes traffic to a dead endpoint.
- Several records with health checks but no failover policy = active-active, not active-passive. The policy name carries
  the distinction.
- Hybrid DNS: inbound resolver endpoint = on-premises resolves names in AWS; outbound endpoint = AWS resolves
  on-premises names. Self-run forwarders on instances are the overhead these remove.
- Resolver DNS Firewall: filters outbound DNS by domain with allow/block lists. Use to restrict which external domains
  instances reach (a security group knows only addresses and ports).
- Cross-account private hosted zone association is CLI/API only; the console does not offer it.

## Load balancing and content delivery

- Load balancer: spreads connections over healthy targets, removes failing ones; solves capacity and failure (single
  server is a SPOF and a ceiling). CDN: caches near users; solves distance (speed of light). Complementary, not
  alternatives; mature public stacks use both.
- Two axes in every decision: layer 4 (connections) vs layer 7 (HTTP), and where in the request path the failover
  decision is made.

### Choosing a load balancer

| Aspect     | ALB                                                                            | NLB                                                                         | GLB (Gateway)                                                               |
| ---------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Layer      | 7 (HTTP/HTTPS)                                                                 | 4 (TCP/UDP)                                                                 | Inline third-party inspection appliances                                    |
| Routing    | Path, host, header, query string                                               | No path routing (does not read request)                                     | Endpoints as route next hop                                                 |
| Static IP  | None                                                                           | One static/elastic IP per AZ                                                | n/a in article                                                              |
| Source IP  | n/a in article                                                                 | Preserves client source address                                             | n/a in article                                                              |
| Cross-zone | On and free                                                                    | Off by default (enabling causes cross-zone data charges)                    | n/a in article                                                              |
| Algorithm  | Round robin, least-outstanding-requests                                        | Flow hash                                                                   | n/a in article                                                              |
| Other      | Weighted target groups, Lambda targets, WAF, WebSockets, HTTP/2, built-in auth | Can take an ALB as a target; classic model has no security group of its own | Only one doing bump-in-the-wire inspection (other two terminate or rewrite) |

- ALB protocol details: HTTP/2 only over HTTPS and only to external clients (onward to targets is HTTP/1.1). No
  port-based TCP routing.
- NLB classic model has no security group, so the target's security group sees the client address directly. "Check the
  security group on the load balancer" has nowhere to go.
- Quick eliminations: UDP rules out ALB; static addresses rules out ALB; WAF or path routing requirement rules out NLB.
- A load balancer is Regional and VPC-bound: never spans Regions or registers targets in another Region; peering does
  not extend it. Targets need not be in its VPC: IP targets can be outside, including on-premises, if routable.
- Anti-pattern: publishing instances' own elastic IPs in DNS. Bypasses the LB: no health checks, no even distribution,
  no failover.

### ALB features worth knowing

- Weighted target groups split traffic between versions. Target group stickiness pins a client to the group it first
  reached. Ordinary session stickiness pins to a target, not a group, so it will not keep a user on one version (canary
  shows both versions otherwise).
- Authentication at the load balancer adds sign-in to an app whose code cannot change; often the only option left. Only
  two authentication actions: Cognito user pools and any OpenID Connect provider. A listener rule only forwards,
  redirects, returns a fixed response, or does one of those two authentications.
- End-to-end TLS and ACM:
  - Old rule: public ACM certificates cannot be exported, so TLS on the instances with an ACM cert was impossible.
  - Since June 2025 exportable public certificates exist: issued with private key for EC2, containers or on-premises;
    priced per name; valid 395 days.
  - Caveats: certificates issued before that launch cannot be exported retroactively; export must be granted via IAM.
  - Terminating TLS on instances otherwise needs a certificate from elsewhere, with the managed cert on the LB
    forwarding to port 443.
  - "Export the managed certificate and install it on each instance" is something the service will not allow (article's
    statement, in tension with the exportable certs above) (check).
- Certificates are Regional. A second Region needs its own certificate requested there; no cross-Region sharing.

### Content delivery

- CloudFront supports seven HTTP methods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE. Anything unusual or non-HTTP
  needs a different accelerator. It accelerates delivery to viewers; speeding uploads into a bucket is a different
  feature.
- Origin groups: in-request failover between primary and secondary origin on configured status codes. No DNS, TTL or
  health-check interval, so the fastest failover; use when the target is seconds. Constraints: a group contains origins,
  not distributions; primary/secondary are fixed, so not a "send each user to the closest Region" mechanism.
- Custom error responses serve a page from another origin for a given status code. Cache behaviors evaluate in
  precedence order (a temporary catch-all behavior can override the default during maintenance).
- Origin incidents:
  - By default CloudFront does not forward the Host header to a custom origin; breaks multi-site-by-hostname origins
    (origin sees CloudFront's hostname, serves wrong site).
  - S3 as origin: REST endpoint and website endpoint differ. Website endpoint: supports redirects and custom error
    documents, but is public. REST endpoint: works with origin access control, can stay private.
- Locking the origin: reference the managed prefix list in the origin's security group, or have CloudFront inject a
  secret custom header that a firewall rule validates. Hard-coded ranges need endless re-editing and the ranges change.
- A CloudFront certificate must be requested in `us-east-1`, wherever the rest of the stack lives.
- Field-level encryption: encrypts nominated form fields at the edge with a public key you upload; only the private key
  holder reads them downstream.

### Edge compute

- CloudFront Functions: viewer request and response only, under 1 ms, no network calls. Good for header rewriting, query
  string normalization, routing decisions; useless where a lookup is needed.
- Lambda@Edge: all four trigger points, can make network calls. A viewer-request trigger cannot modify a response (does
  not exist yet).
- Work that must influence the cache must happen on viewer request, before cache lookup. Origin-request runs only after
  a miss, too late to improve hit ratio.
- Frequently changing content caches poorly, so origin distance dominates: move the origin closer instead of tuning the
  cache.
- Price classes restrict which edge locations serve content. If all users are on one continent, a reduced price class
  cuts cost with no visible effect.
- One distribution can carry many behaviors, origins and paths. A second distribution means a second domain name and a
  DNS change (a real migration); only when a separate identity is needed.

## Edge security: acceleration, firewalls and DDoS

- Global Accelerator: two static anycast addresses; routes over the AWS backbone from the nearest edge; failover in
  seconds, not DNS time.
- Two distinct uses:
  - Static addressing: appliances, partners with firewall rules, gaming clients, IoT fleets need an IP that never
    changes; the two stay fixed while backends move.
  - Fast invisible failover: decision is made inside the connection, no client cache; seconds versus DNS TTL plus
    health-check interval; client never sees a new address.
- Endpoints: load balancers, EC2 instances, elastic IPs. It cannot front a CloudFront distribution, an object store or
  an API gateway.
- Standard type routes to the nearest healthy Region. Custom-routing type is different and not the answer to proximity.

### Four defenses, four different threats

| Service          | What it sees / does                                                                                                      | Use for                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| AWS WAF          | HTTP requests (URL, headers, query string, body), per request                                                            | Injection, XSS, scrapers, abusive clients; wrong for packet floods                                               |
| AWS Shield       | Volume                                                                                                                   | Floods; see below                                                                                                |
| Network Firewall | Everything inside the VPC: stateful rules, Suricata-compatible signatures, protocol detection, outbound domain filtering | Egress control, data exfiltration, non-HTTP; only one that shows what your instances talk to                     |
| Firewall Manager | Inspects nothing; governance layer: one policy across all org accounts, including future ones                            | Central policy for WAF rules, Shield Advanced, security group policies, Network Firewall; reports non-compliance |

- Shield Standard: on for every customer, free, absorbs common network/transport floods automatically.
- Shield Advanced: paid; you buy people and money, not better filtering: DDoS response team access during attacks,
  tunable protections, detailed attack telemetry, cost protection that refunds scaling charges caused by an attack. Cost
  protection decides cases: billed for unwanted traffic means Shield Advanced, not request filtering.
- Mapping: crafted request = WAF; flood = Shield; non-HTTP or outbound = Network Firewall; "across 200 accounts and must
  stay that way" = Firewall Manager. Scenarios often need two; offering one where two are required is the usual trap.

### AWS WAF in practice

- Attaches to: CloudFront, ALB, API Gateway, AppSync, Cognito user pools, App Runner, Verified Access. Never to an EC2
  instance, an NLB or a Directory Service directory.
- Recurring judgments:
  - Count mode observes without blocking (tune before enforcing). The observing action is count, not allow. A web ACL
    left in count mode does not satisfy a block requirement.
  - Rate-based rule handles rotating source addresses; static address lists need endless curation.
  - Managed rule groups are specialized: match the group to the threat (bot control does nothing about injection).
  - Filtering at the edge is cheaper than at the load balancer (blocked requests never reach your network).
  - A firewall matches request attributes; it cannot validate an identity or run an authentication flow.
- Mechanics:
  - Rules evaluate in priority order; first terminating action wins. An allow above a block silently disables the block.
  - Inspected body size is capped: WAF sees the first part of a large payload. An attack deep in a 2 MB upload passes
    uninspected.
  - A custom response lets a blocked request return something the app can recognize (partner systems tell "blocked" from
    "broken").
- Logs to a third-party system go through Amazon Data Firehose, not directly. Logs can be filtered before delivery to
  avoid storing every allowed request.

### Shield, Network Firewall and central enforcement

- Shield Advanced is bought per organization with a meaningful monthly commitment. Justify with a business-critical
  public endpoint or the cost-protection concern. Health-based detection (tell Shield what healthy looks like via a
  Route 53 health check) reduces false positives by separating harmful spikes from harmless ones.
- Network Firewall deploys as an endpoint per AZ; traffic reaches it only via routing (typically a dedicated inspection
  subnet and route tables). Not transparent: forgetting the route table means a deployed firewall inspecting nothing.
- Network Firewall cost: per-endpoint hourly plus per-GB processing. A firewall in each of 30 VPCs is expensive; a
  centralized inspection VPC behind a transit gateway is usually better.
- Firewall Manager prerequisites: AWS Organizations with all features enabled, and a designated administrator account.
  Enforces continuously (a deleted required rule in a member account is restored). Per-account appliance/proxy fleets
  are the opposite of central management and multiply cost.
- Three eliminations:
  - Security groups cannot express geography or log denials.
  - DNS steers but does not block; geolocation routing leaves the resource reachable by address.
  - Amazon Inspector examines resources for known vulnerabilities; it does not inspect live traffic.

## API Gateway

- Managed front door for APIs: terminates HTTPS, authenticates, validates, throttles, forwards to a backend (functions,
  containers, anything reachable over HTTP).
- Centralizes authentication, rate limiting, request validation, versioning, usage metering, consistent errors; backend
  can assume an authenticated, well-shaped request.
- Makes a function reachable from the internet in a controlled way (in nearly every serverless diagram).
- Portability: self-hosted gateways exist; lock-in is the configuration (authorizers, mapping templates, usage plans),
  not the concept.

### The three API types

| Feature                                            | REST | HTTP           | WebSocket |
| -------------------------------------------------- | ---- | -------------- | --------- |
| Usage plans and API keys                           | Yes  | No             | n/a       |
| Request/response mapping templates                 | Yes  | No             | n/a       |
| Web firewall (WAF) support                         | Yes  | No             | n/a       |
| Private endpoints                                  | Yes  | No             | n/a       |
| Request validation                                 | Yes  | n/a in article | n/a       |
| Caching                                            | Yes  | No             | n/a       |
| Cheaper and faster, reduced feature set            | No   | Yes            | n/a       |
| Persistent bidirectional connection, server pushes | No   | No             | Yes       |

- WebSocket: each connection gets an identifier you store; push via a management API. Signal: any requirement where the
  server must initiate (chat, live dashboard, trading feed, job progress). Replaces polling an HTTP endpoint every few
  seconds (anti-pattern). AppSync subscriptions are the managed-GraphQL alternative.
- Choose: usage plans, mapping templates, WAF or private endpoints = REST. Only cost and latency for a simple proxy =
  HTTP. Server push = WebSocket.

### Controlling who can call it

| Mechanism                    | Use when                                                                                  | Notes                                                                                                                                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IAM authorization            | Service-to-service in AWS; callers who already hold IAM identities                        | Signs each request with AWS credentials; only one enforced by AWS's own request signing                                                                                                                                                         |
| Cognito user pool authorizer | App with its own sign-up/sign-in                                                          | Validates user pool token, no code; low effort                                                                                                                                                                                                  |
| Lambda authorizer            | Decision depends on something else: third-party IdP, bespoke token, entitlement in own DB | Your function returns an IAM policy. Token authorizer sees only the bearer token; request authorizer also sees headers, query strings, path parameters. Both support caching keyed on identity source; without it a function runs on every call |
| API keys with usage plans    | Tiering/quotas (e.g. free 100 requests/day, paid 100,000)                                 | Not authentication; identifies caller for metering/throttling only; travels in a header, anyone with it can use it. Pair with a real authorizer                                                                                                 |

- Common brief combines two: Cognito authorizer (identity) plus usage plan (per-customer limits). Offering only one
  where both metering and identity are needed is the trap.

### Stages, deployments and integrations

- An API has no effect until deployed to a stage. Stage holds throttling, caching, logging, variables. Console changes
  do nothing in production until a deployment ("change isn't live" is most often this).
- Stage variables: one API definition points to different backends per stage (dev/test/prod share one definition). With
  a Lambda alias, they route a stage to a specific function version.
- Integration types:
  - Proxy: passes the whole request through; backend returns a correctly shaped response. Simple; the default worth
    using.
  - Non-proxy: mapping templates reshape request/response; needed when the backend contract cannot change (legacy
    service, third-party API, AWS service called directly).
  - API Gateway can call DynamoDB, SQS, Step Functions and others directly with no function in between, removing a
    Lambda, its cost, cold start and code.

### Endpoint types and private access

- Regional: serves callers near the Region. Edge-optimized: fronts with CloudFront's network for distant callers; gives
  nothing when callers are near; not a multi-Region answer (still one Regional API).
- Private APIs: reachable only via an interface endpoint; deny everything until a resource policy grants access. No
  resource policy = closed (most common reason a new private API seems broken).
- Do not exist: a VPN to API Gateway; moving it into your VPC (managed Regional service outside it). The private
  endpoint type achieves the goal. Global Accelerator cannot front it.
- Invoke permission is `execute-api:Invoke`, not an administrative `apigateway:*` action (those manage config, not
  calls). Wrong one is non-working and a quiet over-permission.

### Limits and throttling

- Payload ceiling 10 MB. Larger objects: presigned upload to object storage; the API hands out the URL.
- Per-client rate limiting: usage plans with API keys. Function concurrency caps parallelism, not requests per period,
  and gives no per-client fairness. Client-side exponential backoff cannot stop a flood the client generates; the server
  must throttle.
- Stage caching reduces read load; does nothing for write-heavy problems.
- CORS is a browser mechanism and grants no authorization. Enforced by the browser against the origin actually called;
  configure it on whichever service answers the failing request. Same confusion with object storage: fix is on the
  service returning the response, not the one serving the page.
- App's own sign-in flow: managed user directory (Cognito). IAM Identity Center authenticates people to AWS (employees
  to console, not customers to your API).
- Operational wrinkle: no neat built-in way to move a custom domain from one API to another during a migration. Plan
  traffic movement ahead if replacing an API wholesale.
