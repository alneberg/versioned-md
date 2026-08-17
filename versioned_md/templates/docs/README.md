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
4. Update frontmatter fields:
   - `title`: Display title
   - `description`: Short description for navigation
   - `category`: Must match the parent directory
   - `documentId`: 4-digit numeric for strict/draft (auto-assigned), descriptive for reference
5. For `strict` docs only: rename the file to match its `documentId` (e.g. `1001.md`)

## Promotion to Strict

To promote a draft to a strict document:

1. Move the file from `docs/drafts/` to `docs/strict/`
2. Rename the file to just its 4-digit `documentId` (e.g. `1001.md`)
3. Add any missing required frontmatter fields (`category: strict`, `description`, etc.)
4. Open a PR for review

The CI will automatically validate metadata and update `.meta.json`.

## Metadata

Each document has an accompanying `.meta.json` companion file that stores version history. This is created automatically by the CI system.

When a PR is merged, the following fields are automatically updated in the **changed files only**:
- `prNumber` — the PR that was merged (stored in frontmatter)
- `version` — incremented from the last entry in `.meta.json`
- `lastUpdated` / `updatedBy` — date and author of the merge commit
- `reviewer` — approved reviewers fetched from the PR
- `commitHash` — short SHA of the merge commit

Each entry in `.meta.json`'s `version_history` also records the `pr_number` (null for direct commits) for audit trail purposes.

The CI blocks squash and rebase merges — only "Create a merge commit" is allowed, ensuring every merge has a corresponding PR number and merge commit SHA.

For more information, see the [project README](../README.md).
