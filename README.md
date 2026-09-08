# versioned-md

**Automated metadata management for markdown documentation repositories.**

versioned-md is a CLI tool that bootstraps documentation repositories with automated metadata handling, version tracking, and review governance.

## Purpose

versioned-md enforces versioning on individual markdown documents. The version is a human readable integer but is also tightly coupled to the git commit hash. Additionally the change process for documents is completely piggy-backing on the review process for a pull request in GitHub.

In short, versioned-md enables a few things in addition to plain markdown documents:

- **Versioning of individual documents**: Each document has its own version id, tightly linked to a commit hash.
- **Reviewer tracking**: Know who approved each document
- **Automated governance**: Enforce metadata consistency without manual effort
- **Stable identifiers**: Unique IDs that survive renames and refactoring

The backbone of versioned-md is GitHub Actions workflows and Python tooling to handle all of that automatically.

## Simple Workflow, Powerful Results

Once everything is up and running, for the most common case — updating one or more documents — the workflow is as simple as:

1. **Edit** one or more markdown files in `docs/`
2. **Open a PR**
3. **Get it reviewed** using standard GitHub PR reviews
4. **Merge** — Once merged, CI automatically bumps the version, records who changed what, tracks reviewers, and links to the PR

That's it. No special commands, no manual metadata edits, no separate versioning system to learn.

## A CLI to manage the metadata

For other use-cases - adding new documents, importing history, register a new person, publish a draft document or setting up a new repository - the CLI tool is a useful tool.
The CLI has subcommands:
- **doc** Create, promote (draft -> strict), retire or import (from a different git repository) documents
- **create** Setting up a documentation repository from scratch
- **sync** Get the latest changes in upstream CI scripts
- **people** Add, deactivate or import team members
- **meta** Validate a meta.json file

Please see the [Standard Operating Procedures](#standard-operating-procedures) for instructions for specific use cases.

## How it works

1. **Authors write Markdown docs** in `docs/{strict,drafts,reference}/` — metadata lives in companion `.meta.json` files
2. **Open a PR** — the `check-header.yml` workflow validates that protected metadata isn't tampered with
3. **Review and merge the PR**
4. **Merge triggers updates** — the `update-metadata.yml` workflow runs on every merge to:
    - Bump the version number
    - Record who updated the document and when
    - Store approved reviewers
    - Track the PR number
    - Maintain `version_history` in companion `.meta.json` files
5. **Static output** — any MkDocs, Starlight, or custom tooling can consume the `.meta.json` files at will

## Document Categories

| Category | Directory | Governance |
|---|---|---|
| `strict` | `docs/strict/` | Full governance. Unique 4-digit IDs. Filename must be `<documentId>.md` (e.g., `1001.md`) |
| `drafts` | `docs/drafts/` | Transitional. Lightweight governance. Descriptive filenames OK |
| `reference` | `docs/reference/` | Static reference docs. No governance. Descriptive IDs and names OK |

Documents can be promoted from `drafts` → `strict` via a dedicated PR. The CI handles the rest.

## Installation

Install the tool globally using [the uv package manager](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/your-org/versioned-md.git
```

This makes `versioned-md` available globally — you can run it from any directory to create and manage documentation repositories.

### Bootstrapping a new repository

Run `versioned-md create` without arguments for an interactive prompt, or supply flags for non-interactive use:

```bash
# Non-interactive: supply flags directly
versioned-md create \
  --name my-docs \
  --description "Team documentation repository" \
  --author "Acme Corp"

# Author is used in the LICENSE file; org defaults to author if not specified
versioned-md create \
  --name my-docs \
  --author "Jane Doe" \
  --org "Acme Corp"

# Interactive: run without flags
versioned-md create
```

This bootstraps a new repo with:
- `docs/strict/`, `docs/drafts/`, `docs/reference/` directories
- A `TEMPLATE` branch containing CI workflows, scripts, and Python utilities
- A `main` branch ready for documentation

From inside your new repository:

```bash
# Create your first document as a draft
versioned-md doc create \
  --title "Hello World" \
  --category draft \
  --description "The first document"

# Add more people to your team
versioned-md people add --name "John Smith" --handle "john" --initials "JS"

# Promote a draft to strict
versioned-md doc promote docs/drafts/hello-world.md --category strict

# Push to GitHub
git remote add origin git@github.com:your-org/my-docs.git
git push -u origin main
```

The `TEMPLATE` branch is synced automatically with `versioned-md sync` when CI workflows need updating.

## CLI Reference

### People

```bash
# Add a person to your repo
versioned-md people add --name "Name" --handle "handle" --initials "XX"

# Import people from GitHub contributors + git log
versioned-md people import --dry-run --token "$GITHUB_TOKEN"
```

### Documents

```bash
# Create a new document (requires --category, drafts need a title)
versioned-md doc create --title "Doc Title" --category draft --description "Description"

# Promote a draft to strict
versioned-md doc promote --path docs/drafts/my-doc.md --category strict

# Retire a document
versioned-md doc retire --path docs/strict/1001.md --reason "Replaced by 1020"

# Import an existing Markdown file
versioned-md doc import --source existing-file.md --category draft
```

### Metadata

```bash
# Validate all documents
versioned-md meta validate

# Validate a specific file
versioned-md meta validate --path docs/strict/1001.md
```

### Template sync

```bash
# Sync the TEMPLATE branch with the latest CI workflows
versioned-md sync
```

### Quick Start Commands Explained

The typical workflow for managing documents:

```bash
# 1. Create a draft document (auto-assigns documentId)
versioned-md doc create --title "My Feature" --category draft

# 2. Promote to strict
versioned-md doc promote docs/drafts/my-feature.md --category strict

# 3. Retire a document (moves to docs/retired/)
versioned-md doc retire docs/strict/1001-old-doc.md --reason "Replaced by 1020"
```

### Document Lifecycle

| Command | Purpose | Details |
|---|---|---|
| `doc create` | Create a new document | Prompts for category; drafts get auto-assigned docId, strict asks for a number |
| `doc promote` | Move draft → strict | Renames file, updates category, validates documentId uniqueness |
| `doc retire` | Retire a document | Moves to `docs/retired/`, sets `status: retired` in `.meta.json` |
| `doc import` | Import existing Markdown file | Reads the markdown body, enriches with git history, auto-imports `version_history` from source `.meta.json`, supports `--dry-run` |

### Meta File Management

Each document has a companion `.meta.json` file that tracks `version_history` — a log of all changes made to the document.

```bash
# Validate .meta.json files against the schema
versioned-md meta validate               # check all docs in the repo
versioned-md meta validate -p docs/strict/1001.meta.json  # specific file
versioned-md meta validate -p docs/strict/1001.md          # companion file (auto-discovers .meta.json)
```

The `version_history` array in each `.meta.json` is validated by CI:
- Schema enforcement ensures required fields (`version`, `updated_by`, `last_updated`)
- All fields on existing entries are locked (deep equality check on every field)
- First PRs can include imported history from other repositories
- Post-merge, CI appends entries automatically (skips if already present)

### Version History Schema

```json
{
  "version_history": [
    {
      "version": "1",
      "updated_by": "jane",
      "last_updated": "2024-03-20",
      "reviewer": ["john", "bob"],
      "commit_hash": "abc1234",
      "pr_number": 42,
      "action": "created"
    }
  ]
}
```

### People Management

The `people.json` file is a registry of everyone who is allowed to author or review documentation in the repository. Before a PR can be merged, CI checks that:

- The PR author is listed in `people.json` (to ensure only known individuals contribute)
- Every reviewer who approved the PR is listed in `people.json` (to gate approvals)

When CI detects an unknown author or reviewer, it blocks the PR. Adding people to the registry is therefore a prerequisite to any document workflow.

```bash
# Non-interactive: supply all fields via flags
versioned-md people add --name "Jane Doe" --handle "jane" --initials "JD"

# Interactive: run without flags in a terminal
versioned-md people add

# Deactivate a team member
versioned-md people deactivate --handle "jane"

# Import people from GitHub API + git log
versioned-md people import         # auto-discovers from contributors & git log
versioned-md people import --dry-run   # preview without writing
```

`people import` scans the local git log and (on GitHub repos) the contributors API and PR reviews.
You'll need a `GITHUB_TOKEN` or `--token` to access the GitHub API for full discovery.
Not a GitHub repo — the command falls back to git log only.

You'll need at least one person in `people.json` to create documents. Use `versioned-md people add` or `versioned-md people import` to populate it.

## Metadata Storage

All document metadata is stored in a companion `.meta.json` file alongside each Markdown file. The Markdown body contains no frontmatter — `.meta.json` is the single source of truth.

```json
{
  "title": "System Architecture",
  "description": "A document describing the system architecture",
  "category": "strict",
  "documentId": "1001",
  "responsible": "jane",
  "status": "active",
  "version": "1",
  "lastUpdated": "2026-06-25",
  "updatedBy": "jane",
  "reviewer": ["sarah", "mike"],
  "commitHash": "a1b2c3d",
  "prNumber": "42",
  "version_history": [...]
}
```

### Field Categories

| Type | Fields | Who Changes |
|---|---|---|
| **Mutable** | `title`, `description`, `responsible` | Authors in PRs |
| **Protected** | `category`, `documentId`, `status`, `version`, `lastUpdated`, `updatedBy`, `reviewer`, `commitHash`, `prNumber` | CI only |

The `responsible` field tracks the person owning the document. It is user-mutable and independent of git committer metadata.

### Schema Rules Enforced by CI

- `category` must match the document's parent directory (`strict`, `draft`, or `retired`)
- `documentId` must be a unique 4-digit number for `strict` and `draft` categories
- `strict` filenames must equal the `documentId` (e.g., `1001.md`)
- `version_history` entries are immutable once written; only appending new entries is allowed
- Protected top-level fields cannot be changed in a PR
- Mutable fields (`title`, `description`, `responsible`) can only change if the Markdown body also changed

### Importing Documents

Use `versioned-md doc import` to bring existing Markdown files into the versioned-md structure. By default, if the source file has a companion `.meta.json`, its `version_history` is automatically merged:

```bash
# Full import with version_history
versioned-md doc import -s my-file.md -c draft

# Skip version_history merging
versioned-md doc import -s my-file.md -c draft --skip-history
```

The `--skip-history` flag disables automatic `version_history` merging from the source `.meta.json`, useful when importing documents that already exist in the target repo.

## Standard Operating Procedures

Step-by-step guides for common documentation workflows. These ship with every repository created by `versioned-md create` and are available in `docs/sop/` after bootstrapping.

- [Getting Started](versioned_md/templates/docs/sop/01-getting-started.md) — Create a repo from scratch, bootstrap with people and first document
- [Creating Documents](versioned_md/templates/docs/sop/02-creating-docs.md) — Drafts, strict documents, and reference docs
- [Document Lifecycle](versioned_md/templates/docs/sop/03-document-lifecycle.md) — Promote drafts to strict, retire outdated docs, import from elsewhere
- [Team Management](versioned_md/templates/docs/sop/04-team-management.md) — Add people, bulk import from GitHub, deactivate team members
- [CI & Governance](versioned_md/templates/docs/sop/05-ci-governance.md) — The PR workflow, CI checks, and what happens on merge
- [Maintenance & Admin](versioned_md/templates/docs/sop/06-maintenance-admin.md) — Update CI templates, validate metadata, migrate legacy repos
- [Reference](versioned_md/templates/docs/sop/07-reference.md) — Field reference (mutable vs protected), version history rules, troubleshooting

You can also open these from your own repo after running `versioned-md create`:

```bash
# View the SOPs in your local docs directory
ls docs/sop/
```

## Development

```bash
uv sync               # install runtime deps + package
uv pip install -e ".[dev]"  # add dev deps
uv run ruff check .   # lint
uv run ruff format .  # format
```

## License

MIT License — see [LICENSE](LICENSE) for details.
