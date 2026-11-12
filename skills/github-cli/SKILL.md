---
name: github-cli
description:
  Use when pushing branches, opening or stacking pull requests, or creating issues with `gh` and `git push`, and when
  `gh` fails with a GraphQL error such as "Base ref must be a branch".
---

# GitHub CLI and git push

## Before any `gh pr create`

1. `gh auth status` must show a logged-in account. Git itself may use SSH while `gh` uses its own token.
2. The base branch must exist on origin: `git ls-remote --heads origin <base>`. If it is missing, push it first.
3. Push in stack order: the base, then the head. `git push -u origin <branch>`.
4. The head must have commits the base lacks, or `gh` reports "No commits between".

## The GraphQL error

`GraphQL: Head sha can't be blank, Base sha can't be blank, No commits between X and Y, Base ref must be a branch (createPullRequest)`
means `gh` could not find the base (or head) branch on GitHub. It is not a `gh` bug and retrying does nothing. Push the
missing branch, then run the same `gh pr create` again.

## Stacked draft PRs

```bash
gh pr create --base main --head factory/01-x --title "01 x" --body-file body.md
gh pr create --base factory/01-x --head factory/02-y --title "02 y" --body-file body2.md
```

- The title of the PR should be in the format: `{feat|test|doc} [{TICKET_ID}]: {Ticket title}`. For example:
  `feat [T-21]: Add authentification to the web app`
- The PR description follows this format (in a repo with `.github/pull_request_template.md`, that file is the source):

  ```markdown
  # {TICKET_ID}: {TICKET TITLE}

  {Ticket description}

  - [x] {Acceptance criterion or task that is done}
  - [ ] {Acceptance criterion or task that is still open}

  ## What changed

  {Changes, the most significant first}

  ## Tests

  {Test results: unit, e2e}

  {Screenshots, if applicable}
  ```

  `--body-file` skips the template, so write the body file in this format yourself.

- `gh pr list --state all --json number,baseRefName,headRefName,state` shows the stack.
- Retargeting after a base is merged: `gh pr edit <n> --base main`.

## Issues

`gh issue create --repo OWNER/REPO --title "..." --body-file file.md [--label a,b]`. Creating issues in a public
repository publishes the text: confirm the repository with the user when the content belongs to another project.

Ticket files to issues: `python3 <skill-dir>/scripts/tickets_to_issues.py DIR` (`<skill-dir>` is this skill's base directory) is a dry run for the repo
in the current directory; `--create` makes the missing issues and `--update` rewrites the ones whose body differs from
the file. It closes a new issue when the file says `**Status:** done`; close an already open one yourself.

## "Resource not accessible by personal access token"

`gh` fails with this on `gh pr merge`, `gh pr checks`, `gh run list` or `gh pr list --json statusCheckRollup` (HTTP 403)
when the shell exports `GITHUB_TOKEN` (a limited fine-grained token). The variable overrides the keyring login, which
has the `repo` scope. Check with `gh auth status`: the active account says `(GITHUB_TOKEN)` instead of `(keyring)`.
Run the command without the variable, no change to the shell or settings needed:

```
env -u GITHUB_TOKEN gh pr merge 126 --merge
```

For several PRs wrap the loop: `for n in ...; do env -u GITHUB_TOKEN gh pr merge $n --merge; done`. The permanent fix
is a token with Pull requests, Actions and Checks read/write, or removing the export. Do not paste either token.

## Rules

- No `Co-Authored-By: Claude` or other Claude attribution in commits or PR bodies (the user's global rule).
- Force-push only with the user's go-ahead, and then `git push --force-with-lease=<branch>:<expected-sha>`, never
  `--force`. Rewriting a pushed branch needs it; the harness may refuse it, in which case print the command.
- Never force push to `main` branch!
- Pushing and opening PRs is outward-facing: do it when asked, otherwise print the commands.
- the `<base>` called `main`, not `master`
