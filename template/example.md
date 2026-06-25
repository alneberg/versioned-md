---
title: "Example Documentation Page"
description: "A sample document demonstrating the metadata schema."
category: draft
documentId: "1001"
lastUpdated: 2026-06-25
updatedBy: johannes
reviewer:
  - jane
  - mike
version: "1"
commitHash: "a1b2c3d"
---

# Example Documentation Page

This is a sample document that demonstrates the metadata schema used across all
documents in the documentation system.

## Purpose

It serves as a template for authors writing new documents. You can copy this
file and adapt it as a starting point.

## Frontmatter Fields

| Key | Description |
|---|---|
| `title` | Display title, required by MkDocs/Starlight |
| `description` | Short description for SEO/navigation |
| `documentId` | Stable 4-digit identifier (auto-assigned for strict/draft) |
| `category` | Must match parent directory (`strict`, `draft`, or `reference`) |
| `lastUpdated` | Date of last metadata update (ISO 8601) |
| `updatedBy` | GitHub handle of the person who triggered the update |
| `reviewer` | List of approved reviewers |
| `version` | Sequential version number (string to preserve leading zeros) |
| `commitHash` | Short Git SHA of the merge commit that performed this update |

## Document Categories

- **`strict`** (in `docs/strict/`): Full governance, unique 4-digit `documentId`, requires promotion from drafts. **Filename must be `<documentId>.md`** (e.g., `1001.md`).
- **`draft`** (in `docs/drafts/`): In-progress work. `documentId` is auto-assigned on first merge. Descriptive filenames OK.
- **`reference`** (in `docs/reference/`): Independent reference docs, less strict governance. Descriptive `documentId` and filenames allowed.

## Document IDs

Documents in `strict` and `draft` categories receive a **4-digit numeric documentId** (e.g. `1001`, `1002`).
IDs start at `1001` and are auto-advanced by the CI on each new merge. Reference docs may use descriptive IDs.

## Promotion to Strict

To promote a draft to strict:

1. Move the file from `docs/drafts/` to `docs/strict/`.
2. Rename the file to just its 4-digit `documentId` (e.g., `1001.md`). **This is required — strict filenames must not include a title component.**
3. The existing `documentId` is carried over (no reassignment needed).
4. Update frontmatter to include `category: strict` and any missing fields.
5. Open a PR. A reviewer will approve the promotion.
