# Documentation

This directory contains the documentation for our project. Documents are organized into three categories based on their governance level.

## Directory Structure

| Directory | Category | Governance | Filename Rules |
|---|---|---|---|
| `strict/` | `strict` | Full governance, 4-digit IDs, annual review | Must be `<documentId>.md` (e.g. `1001.md`) |
| `drafts/` | `draft` | Transitional, lightweight governance | Descriptive names OK (e.g. `new-pipeline.md`) |
| `reference/` | `reference` | Independent, less strict governance | Descriptive names OK (e.g. `glossary.md`) |

## Creating a New Document

1. Choose the appropriate category based on your document's purpose
2. Copy `template/example.md` as a starting point
3. Place the file in the correct subdirectory
4. Run `versioned-md doc create` to generate the companion `.meta.json` file

For `strict` documents:
- Provide a 4-digit documentId (e.g., `1001`)
- The filename must match the documentId (e.g., `1001.md`)

For `draft` documents:
- DocumentId is auto-assigned by the system
- Descriptive filenames are allowed

## Promotion to Strict

To promote a draft to a strict document:

1. Move the file from `docs/drafts/` to `docs/strict/`
2. Rename the file to just its 4-digit `documentId` (e.g. `1001.md`)
3. Run `versioned-md doc promote` to update metadata
4. Open a PR for review

The CI will automatically validate metadata and update `.meta.json`.

## Metadata

All document metadata is stored in companion `.meta.json` files alongside each Markdown file. The Markdown body contains no frontmatter — `.meta.json` is the single source of truth.

The `.meta.json` file contains:
- `version_history` — log of all document changes (version, author, date, reviewers)
- Top-level fields like `title`, `description`, `category`, `documentId`, `status`, `version`, `lastUpdated`, `updatedBy`, `reviewer`, etc.

When a PR is merged, the `update-metadata.yml` workflow runs automatically to:
- Update `version`, `lastUpdated`, `updatedBy` in `.meta.json`
- Add entries to `version_history`
- Store `commitHash`, `prNumber`, and `reviewer`

The CI blocks squash and rebase merges — only "Create a merge commit" is allowed, ensuring every merge has a corresponding PR number and merge commit SHA.

## SOPs

Standard Operating Procedures for common documentation workflows:

- [Getting Started](sop/01-getting-started.md) — Create a repo, bootstrap for first use
- [Creating Docs](sop/02-creating-docs.md) — Drafts, strict, and reference documents
- [Document Lifecycle](sop/03-document-lifecycle.md) — Promote, retire, and import documents
- [Team Management](sop/04-team-management.md) — Adding people, bulk imports, deactivation
- [CI & Governance](sop/05-ci-governance.md) — The PR workflow, CI checks, and post-merge automation
- [Maintenance & Admin](sop/06-maintenance-admin.md) — Updating CI, validating metadata, migrating legacy repos
- [Reference](sop/07-reference.md) — Field reference, version history rules, and troubleshooting

For more information, see the [project README](../README.md).
