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

## Quick Start

```bash
# Clone and install locally
git clone https://github.com/your-org/versioned-md.git
cd versioned-md
uv sync

# Create a new documentation repository
mkdir my-docs && cd my-docs
uv run versioned-md create

# Add an initial person (required for people.json)
uv run versioned-md people add --name "Jane Doe" --handle "jane" --initials "JD"
```

This bootstraps a new repo with:
- `docs/strict/`, `docs/drafts/`, `docs/reference/` directories
- A `TEMPLATE` branch containing CI workflows, scripts, and Python utilities
- A `main` branch ready for documentation

```bash
# Create your first document as a draft
uv run versioned-md doc create \
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
# Add a person to your repo
versioned-md people add --name "Name" --handle "handle" --initials "XX"

# Import people from GitHub + git log
versioned-md people import [--dry-run] [--token TOKEN]

# Manage documents
versioned-md doc create [options]     # Create a new document
versioned-md doc promote [options]    # Promote draft → strict
versioned-md doc retire [options]     # Retire a document
versioned-md doc import [options]     # Import an existing markdown file

# Synchronize the TEMPLATE branch with the latest CI workflows
versioned-md sync
```

### Quick Start Commands Explained

The typical workflow for managing documents:

```bash
# 1. Create a draft document (auto-assigns documentId)
versioned-md doc create --title "My Feature" --category draft

# 2. Promote to strict
versioned-md doc promote docs/drafts/abc-my-feature.md --category strict

# 3. Retire a document (moves to docs/retired/)
versioned-md doc retire docs/strict/1001-old-doc.md --reason "Replaced by 1020"
```

### Document Lifecycle

| Command | Purpose | Details |
|---|---|---|
| `doc create` | Create a new document | Prompts for category; drafts get auto-assigned docId, strict asks for a number |
| `doc promote` | Move draft → strict | Renames file, updates category, validates documentId uniqueness |
| `doc retire` | Retire a document | Moves to `docs/retired/`, sets `status: retired` in `.meta.json` |
| `doc import` | Import existing Markdown file | Extracts frontmatter, enriches with git history, auto-imports `version_history` from source `.meta.json`, supports `--dry-run` |

### Meta File Management

Each document has a companion `.meta.json` file that tracks `version_history` — a log of all changes made to the document.

```bash
# Validate .meta.json files against the schema
versioned-md meta validate               # check all docs in the repo
versioned-md meta validate -p docs/strict/1001.md.meta.json  # specific file
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

The `people.json` file tracks team members who author and review documentation.

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
  "description": "High-level NGI architecture overview",
  "category": "strict",
  "documentId": "1001",
  "responsible": "johannes",
  "status": "active",
  "version": "1",
  "lastUpdated": "2026-06-25",
  "updatedBy": "johannes",
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

## Development

```bash
uv sync               # install runtime deps + package
uv pip install -e ".[dev]"  # add dev deps
uv run ruff check .   # lint
uv run ruff format .  # format
```

## License

MIT License — see [LICENSE](LICENSE) for details.
