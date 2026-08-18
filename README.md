# versioned-md

**Automated metadata management for markdown documentation repositories.**

versioned-md is a CLI tool that bootstraps fully managed documentation repositories with automated metadata handling, version tracking, and review governance.

## Purpose

versioned-md enforces versioning on individual markdown documents. The version is a human readable integer but is also tightly coupled to the git commit hash. Additionally the change process for documents is completely piggy-backing on the review process for a pull request in github.

In short, versioned-md enables a few things in addition to simple markdown documents:

- **Versioning of individual documents**: Each document has its own version id, tightly linked to a commit hash.
- **Reviewer tracking**: Know who approved each document
- **Automated governance**: Enforce metadata consistency without manual effort
- **Stable identifiers**: Unique IDs that survive renames and refactoring

The backbone of versioned-md is Github Actions workflows and Python tooling to handle all of that automatically.

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

## Quick Start

```bash
# Clone and install locally
git clone https://github.com/your-org/versioned-md.git
cd versioned-md
uv sync

# Create a new documentation repository
mkdir my-docs && cd my-docs

# Initialise with an initial person (required for people.json)
uv run versioned-md init . \
  --person-name "Jane Doe" \
  --person-handle "jane" \
  --person-initials "JD"
```

This bootstraps a new repo with:
- `docs/strict/`, `docs/drafts/`, `docs/reference/` directories
- A `TEMPLATE` branch containing CI workflows, scripts, and Python utilities
- `people.json` with your initial person
- A `main` branch ready for documentation

```bash
# Create your first document as a draft
uv run versioned-md doc create docs/drafts/hello-world.md \
  --title "Hello World" \
  --category draft \
  --description "The first document"

# Add more people to your team
uv run versioned-md people add --name "John Smith" --handle "john" --initials "JS"

# Promote a draft to strict
uv run versioned-md doc promote docs/drafts/1001-hello-world.md --category strict

# Push to GitHub
git remote add origin git@github.com:your-org/my-docs.git
git push -u origin main
```

The `TEMPLATE` branch is synced automatically with `versioned-md sync` when CI workflows need updating.

## CLI Reference

```bash
# Initialise template branches and create people.json
versioned-md init --person-name "Name" --person-handle "handle" --person-initials "XX"

# Add a person to an existing repo
versioned-md people add --name "Name" --handle "handle" --initials "XX"

# Create, promote, or deactivate documents
versioned-md doc create [options]    # Create a new document
versioned-md doc promote [options]   # Promote draft → strict
versioned-md doc deactivate [options]    # Deactivate a document

# Synchronize the TEMPLATE branch with the latest CI workflows
versioned-md sync
```

### Quick Start Commands Explained

The typical workflow for managing documents:

```bash
# 1. Create a draft document (CI auto-assigns a documentId)
versioned-md doc create docs/drafts/my-feature.md --title "My Feature" --category draft

# 2. Promote to strict (CI auto-renames to documentId.md)
versioned-md doc promote docs/drafts/1001-my-feature.md --category strict

# 3. Deactivate a document (moves to docs/deactivated/)
versioned-md doc deactivate docs/strict/1001-old-doc.md --reason "Replaced by 1020"
```

### Document Lifecycle

| Command | Purpose | Details |
|---|---|---|
| `doc create` | Create a new document | Writes frontmatter with title, category, auto-assigned documentId |
| `doc promote` | Move draft → strict | Renames file, updates category, validates documentId uniqueness |
| `doc deactivate` | Archive a document | Moves to `docs/deactivated/`, adds `status: deactivated` to frontmatter |

### People Management

The `people.json` file tracks team members who author and review documentation.

```bash
# Non-interactive: supply all fields via flags
versioned-md people add --name "Jane Doe" --handle "jane" --initials "JD"

# Interactive: run without flags in a terminal
versioned-md people add

# Deactivate a team member
versioned-md people deactivate --handle "jane"
```

When initialising a new repo, the same fields are collected:

```bash
# Non-interactive
versioned-md init --person-name "Jane Doe" --person-handle "jane" --person-initials "JD"

# Interactive (TTY)
versioned-md init
```

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

## Development

```bash
uv sync                           # install runtime deps + package
uv pip install -e ".[dev]"        # add ruff
uv run ruff check .               # lint
uv run ruff format .              # format
uv run versioned-md init .        # use the CLI
```

## License

MIT License — see [LICENSE](LICENSE) for details.
