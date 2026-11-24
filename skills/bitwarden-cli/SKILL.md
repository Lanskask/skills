---
name: bitwarden-cli
description:
  Use when a task needs a secret, password, API key, username or TOTP code from the user's Bitwarden vault with the `bw`
  CLI, or when `bw` reports a locked vault, "Vault is locked" or an invalid session.
---

# Bitwarden CLI (`bw`)

The goal is to use a secret without it ever appearing in the conversation.

## Before any `bw` call

1. `bw status` prints JSON. `"status": "unlocked"` is required. If it says `locked` or `unauthenticated`, stop and tell
   the user to run this in their own terminal, then restart `claude` from the same shell:

   ```bash
   bw login                               # once, if unauthenticated
   export BW_SESSION="$(bw unlock --raw)"
   ```

   `BW_SESSION` is the session key that `bw` reads from the environment. Each Bash call starts a fresh shell, so the key
   must be inherited from the shell that launched Claude Code.

2. Never ask for the master password, never run `bw unlock` or `bw login` yourself, never write `BW_SESSION` to a file.
3. Add `--nointeraction` to every call so `bw` fails instead of waiting for a prompt.

## Find an item without exposing secrets

`bw list items` returns full records, passwords included. Always reduce the output to harmless fields:

```bash
bw list items --search github --nointeraction | jq '[.[] | {id, name, user: .login.username}]'
```

If the search returns several items, ask the user which `id` to use. `bw get <name>` fails on ambiguous names; use the
`id` instead.

## Use a secret

Feed it straight into the command that needs it, inside `$(...)`. Do not print it, `echo` it, assign it to a variable
whose value you then show, or put it in a file in the repo.

```bash
curl -H "Authorization: Bearer $(bw get password <id> --nointeraction)" https://api.example.com/me
bw get totp <id> --nointeraction          # 6-digit one-time code, only when the user asks for it
bw get username <id> --nointeraction
```

- Never run `bw get item` or `bw list items` without a `jq` filter, and never show the unfiltered output.
- Custom fields: `bw get item <id> | jq -r '.fields[] | select(.name=="X") | .value'` goes inside `$(...)` too.
- If a command echoes the secret back (verbose flags, error messages), do not quote that part in your reply.

## Changes and sync

- `bw create`, `bw edit`, `bw delete`, `bw share` change the vault: show the exact command and wait for the user's
  go-ahead.
- If an item the user just added is missing, run `bw sync` once and search again.
- Do not run `bw lock` or `bw logout` unless asked; they end the session for the user's other terminals too.
