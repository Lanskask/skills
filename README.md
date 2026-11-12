# skills

Agent skills I wrote for Claude Code. Each one is a folder under `skills/` with a `SKILL.md`, and most push the
mechanical work into scripts so the model spends few tokens.

## Skills

| Skill                                           | What it does                                                                                             |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [`disk-cleanup`](skills/disk-cleanup)           | Ranks caches, build dirs and big files by size and safety, deletes the safe ones (macOS, Linux, Windows) |
| [`book-to-course`](skills/book-to-course)       | Turns a PDF book or a page range into an interactive HTML course with cited pages                        |
| [`youtube-to-course`](skills/youtube-to-course) | Turns a YouTube video, playlist or time range into an interactive HTML course with timestamps            |
| [`openapi-optimizer`](skills/openapi-optimizer) | Splits and compresses large OpenAPI/Swagger specs so agents read 60-95% fewer tokens                     |
| [`github-cli`](skills/github-cli)               | Pushing branches, stacked PRs and issues with `gh`, and fixes for its common errors                      |

## Install

All or some skills, into any agent the [skills CLI](https://github.com/vercel-labs/skills) supports (Claude Code,
Cursor, Codex and others):

```bash
npx skills add Lanskask/skills                        # all skills
npx skills add Lanskask/skills --list                 # browse first
npx skills add Lanskask/skills --skill disk-cleanup   # one skill
```

As a Claude Code plugin (all skills, invoked as `/lanskask-skills:<name>`):

```text
/plugin marketplace add Lanskask/skills
/plugin install lanskask-skills@lanskask
```

By hand: copy one folder from `skills/` into `~/.claude/skills/` (all your projects) or `.claude/skills/` (one project).

Each skill's README lists what it needs: `disk-cleanup` only Python 3.9+, the course skills
[`uv`](https://docs.astral.sh/uv/) (and `yt-dlp` for YouTube).

## Credits

`book-to-course` and `youtube-to-course` are based on
[zarazhangrui/codebase-to-course](https://github.com/zarazhangrui/codebase-to-course): they reuse its course format,
styles and HTML scripts, with new pipelines for PDF books and YouTube videos.

## Develop

`make` lists the commands: `make validate` checks the plugin manifests, `make test` runs each skill's tests. To add a
skill, create `skills/<name>/SKILL.md` with `name` and `description` frontmatter and add a row to the table above.
