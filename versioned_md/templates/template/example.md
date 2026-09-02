# Example Documentation Page

This is a sample document that demonstrates the metadata schema used across all
documents in the documentation system.

## Purpose

It serves as a template for authors writing new documents. You can copy this
file and adapt it as a starting point.

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
