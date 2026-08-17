# {{ name }}

**{% if description %}{{ description }}{% else %}Documentation repository{% endif %}.**

Automated metadata management for markdown documentation repositories, powered by
[versioned-md](https://github.com/nf-core/tools). This repo manages version history, reviewers,
and document lifecycle using git workflows — forking is all that's needed to use the tooling.

{% if org == "nf-core" or author == "National Genomics Infrastructure (NGI), SciLifeLab" %}
Born at the National Genomics Infrastructure (NGI), Sweden.
{% endif %}

## Purpose

versioned-md enforces versioning on individual markdown documents. The version is a human readable
integer but is also tightly coupled to the git commit hash. Additionally the change process for
documents is completely piggy-backing on the review process for a pull request in GitHub.

In short, versioned-md enables:

- **Versioning of individual documents**: Each document has its own version id, tightly linked to a commit hash.
- **Reviewer tracking**: Know who approved each document
- **Automated governance**: Enforce metadata consistency without manual effort
- **Stable identifiers**: Unique IDs that survive renames and refactoring

The backbone of versioned-md is GitHub Actions workflows and Python tooling that handles all of this
automatically.

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
5. **Static output** — any MkDocs, Starlight, or custom tooling can consume the frontmatter + `.meta.json` files

## Document Categories

| Category | Directory | Governance |
|---|---|---|
| `strict` | `docs/strict/` | Full governance. Unique 4-digit IDs. Filename must be `<documentId>.md` |
| `drafts` | `docs/drafts/` | Transitional. Lightweight governance. Descriptive filenames OK |
| `reference` | `docs/reference/` | Static reference docs. No governance. Descriptive IDs and names OK |

Documents can be promoted from `drafts` → `strict` via a dedicated PR. The CI handles the rest.

## Template Updates

This repo was bootstrapped from the versioned-md template. To update the infrastructure (CI scripts,
workflow files, helpers) to the latest version, run:

```bash
pip install versioned-md --upgrade
versioned-md sync
```

This will create a PR from the `TEMPLATE` branch into `main` that you can review and merge.

## Quick Start

1. Create documentation files in `docs/strict/`, `docs/drafts/`, or `docs/reference/`
2. Use `template/example.md` as a starting point
3. Open PRs — metadata is updated automatically on merge

See [docs/README.md](docs/README.md) for detailed instructions on creating and formatting documents.

## License

MIT License — see [LICENSE](LICENSE) for details.
