---
name: duckdns-api
description:
  Use when updating or clearing a DuckDNS (duckdns.org) subdomain's IPv4/IPv6 address, or setting a TXT record (for
  example a Let's Encrypt DNS challenge) through the DuckDNS HTTP API.
---

# DuckDNS API

Source: https://www.duckdns.org/spec.jsp. One endpoint does everything. Always use HTTPS (HTTP exists only for networks
that block HTTPS).

The token is a secret. Read it from the environment as `$DUCKDNS_TOKEN`; never print it, never paste it into the
conversation or a file. If it is unset, tell the user to export it in the shell that launched Claude Code.

## Update an address

```bash
curl -s "https://www.duckdns.org/update?domains=SUB&token=$DUCKDNS_TOKEN&verbose=true"
```

| Parameter | Required | Meaning                                                                                |
| --------- | -------- | -------------------------------------------------------------------------------------- |
| `domains` | yes      | Subname only (no `.duckdns.org`); a comma-separated list updates several               |
| `token`   | yes      | Account token                                                                          |
| `ip`      | no       | IPv4 or IPv6 address. Blank means the caller's IPv4 is auto-detected (IPv4 only)       |
| `ipv6`    | no       | IPv6 address; set it with `ip` to update both records. Disables auto-detection of `ip` |
| `verbose` | no       | `true` adds detail lines to the reply                                                  |
| `clear`   | no       | `true` ignores every IP and clears both the IPv4 and IPv6 records                      |

Examples: add `&ip=1.2.3.4` for a fixed IPv4, `&ipv6=2001:db8::1` for IPv6, `&clear=true` to clear.

## Set or clear a TXT record

```bash
curl -s "https://www.duckdns.org/update?domains=SUB&token=$DUCKDNS_TOKEN&txt=VALUE&verbose=true"
```

- `txt` is required; `clear=true` ignores it and clears the TXT record.
- The record also answers for every sub-subdomain: `a.SUB.duckdns.org` returns the TXT of `SUB.duckdns.org`.
- With `verbose=true`, the reply to `clear=true&txt=x` still echoes `x`; the record is cleared (checked with `dig`).
- It does not show in the web UI. Check with `dig SUB.duckdns.org TXT`.

## Reading the reply

- Plain: `OK` (success) or `KO` (failure; the API gives no reason, so recheck the token and subname).
- With `verbose=true`, `OK` is followed by the current IPv4, the current IPv6 (either may be blank) or the TXT value,
  then `UPDATED` or `NOCHANGE`.

## Routers that cannot send parameters

```text
https://duckdns.org/update/DOMAIN/TOKEN[/IP]
```

Only one subdomain per request; `IP` is optional (IPv4 or IPv6). The token sits in the URL path, so avoid it unless the
device forces it.

## Limits

The spec states no rate limits. Do not call the endpoint in a loop; update only when the address actually changes.

Machine-readable spec: `openapi.yaml` in this folder.
