# versioned-md

**Automated metadata management for markdown documentation repositories.**

A template repository for markdown documentation, developed at the National Genomics Infrastructure (NGI), Sweden. versioned-md can manage version history, reviewers, and document lifecycle using git repos — forking is all that's needed to use it.

## Purpose

versioned-md enforces versioning on individual markdown documents. The version is a human readable integer but is also tightly coupled to the git commit hash. Additionally the change process for documents is completely piggy-backing on the review process for a pull request in github.

In short, versioned-md enables a few things in addition to simple markdown documents:

- **Versioning of individual documents**: Each document has its own version id, tightly linked to a commit hash.
- **Reviewer tracking**: Know who approved each document
- **Automated governance**: Enforce metadata consistency without manual effort
- **Stable identifiers**: Unique IDs that survive renames and refactoring

The backbone of versioned-md is Github Actions workflows and Python tooling to handle all of that automatically.
It was developed to utilize the github UI as much as possible, but should in principle be possible to be adapted to other git hosting services.

## How It Works

1. **Authors write Markdown docs** in `docs/{strict,drafts,reference}/` with YAML frontmatter
2. **Open a PR** — the `check-header.yml` workflow validates that protected metadata isn't tampered with
3. **Review and merge the PR**
4. **Merge triggers updates** — the `update-metadata.yml` workflow runs on every merge to:
    - Bump the version number
    - Record who updated the document and when
    - Store approved reviewers
    - Track the PR number (in both frontmatter and `.meta.json`)
    - Maintain `version_history` in companion `.meta.json` files
5. **Static output** — any MkDocs, Starlight, or custom tooling can consume the frontmatter + `.meta.json` files at will

## Document Categories

| Category | Directory | Governance |
|---|---|---|
| `strict` | `docs/strict/` | Full governance. Unique 4-digit IDs. Filename must be `<documentId>.md` (e.g., `1001.md`) |
| `drafts` | `docs/drafts/` | Transitional. Lightweight governance. Descriptive filenames OK |
| `reference` | `docs/reference/` | Static reference docs. No governance. Descriptive IDs and names OK |

Documents can be promoted from `drafts` → `strict` via a dedicated PR. The CI handles the rest.

## What You Get When You Fork

| Component | Description |
|---|---|
| `pyproject.toml` | Python project config with `pyyaml` and `requests` |
| `lib/metadata.py` | Core library: parse/write frontmatter, manage version history, generate document IDs |
| `lib/reviewers.py` | GitHub API helper to fetch approved reviewers |
| `.github/scripts/` | CI scripts for header validation and metadata updates |
| `.github/workflows/` | GitHub Actions: `check-header.yml` (PR blocking) + `update-metadata.yml` (post-merge automation) |
| `template/example.md` | Complete frontmatter schema reference |

The markdown docs should populate the `docs` directory of the **forked repository** — this repo is just the infrastructure.

## Quick Start

1. Fork this repository
2. Clone your fork
3. Create documentation files in `docs/strict/`, `docs/drafts/`, or `docs/reference/`
4. Use `template/example.md` as a starting point
5. Open PRs — metadata is updated automatically on merge

## Example Frontmatter

```yaml
---
title: "System Architecture"
description: "High-level NGI architecture overview"
category: strict
documentId: "1001"
lastUpdated: 2026-06-25
updatedBy: johannes
reviewer:
  - sarah
  - mike
prNumber: "42"
version: "1"
commitHash: "a1b2c3d"
---

# Document body here...
```

See `template/example.md` for the complete field reference.

## Development

Install dependencies:

```bash
pip install -e .
```

Run locally for testing:

```bash
# Check a PR's metadata
python .github/scripts/check-header.py --base-ref BASE_SHA --pr-ref PR_SHA --file docs/strict/1001.md

# Update metadata (requires GITHUB_TOKEN)
python .github/scripts/update-metadata.py --repo owner/name
```

## Origin

Born at the National Genomics Infrastructure (NGI), Sweden, to solve the problem of managing consistent, auditable documentation that is still smooth to update.

## License

MIT License — see [LICENSE](LICENSE) for details.
