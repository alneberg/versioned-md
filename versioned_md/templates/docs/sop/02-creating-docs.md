# Creating Documents

Standard operations for creating new documents in each category.

---

## SOP 1: Create a Draft Document

**When to use this** — You are writing a document that is still a work in progress. Drafts go into `docs/drafts/` and receive an auto-assigned documentId on first merge.

### Prerequisites

- A `people.json` file exists in the repository
- At least one person is in `people.json`

### Steps

```bash
# Navigate to your documentation repository
cd my-team-docs

# Create a draft document (non-interactive)
uv run versioned-md doc create \
  --title "New Feature Guide" \
  --category draft \
  --description "How to use the new search feature"
```

This creates:

- `docs/drafts/new-feature-guide.md` — plain Markdown (no frontmatter)
- `docs/drafts/new-feature-guide.meta.json` — companion metadata file with auto-assigned documentId

### Interactive mode

Run without flags:

```bash
uv run versioned-md doc create
```

You'll be prompted for:

1. Document title (required)
2. Category (1 = draft, 2 = strict)
3. Description (required)

If you choose draft, the filename is a slug of the title and the documentId is auto-assigned from the global counter.

### Expected outcome

A `.meta.json` file like:

```json
{
  "title": "New Feature Guide",
  "description": "How to use the new search feature",
  "category": "draft",
  "documentId": "1001",
  "status": "active",
  "version": "0",
  "lastUpdated": "2024-01-15",
  "updatedBy": "jane",
  "reviewer": [],
  "commitHash": "",
  "prNumber": "",
  "version_history": []
}
```

The `version` is `"0"` because the document hasn't been merged yet. It will become `"1"` after the first CI merge.

### Notes

- Drafts use descriptive filenames (e.g., `new-feature-guide.md`). This is fine for drafts
- The documentId is auto-assigned from the next value in `.doc_id_counter.json` (defaults to 1001)
- The counter persists between runs — no duplicate documentIds will be generated
- Draft documents can be promoted to strict once they are ready for review

---

## SOP 2: Create a Strict Document

**When to use this** — You are creating a document that is ready to go straight into the `docs/strict/` directory, requiring a 4-digit documentId and matching filename.

### Prerequisites

- A `people.json` file exists in the repository

### Steps

```bash
# Create a strict document, specifying a 4-digit documentId
uv run versioned-md doc create \
  --title "System Architecture" \
  --category strict \
  --description "High-level architecture overview for new team members"
```

You'll then be prompted for the 4-digit document number:

```
Document number (e.g. 1001):
> 1001
```

This creates:

- `docs/strict/1001.md` — filename matches documentId exactly
- `docs/strict/1001.meta.json` — companion metadata

### Interactive mode

Run without flags to be prompted for everything including the document number.

### Expected outcome

- A file named `1001.md` in `docs/strict/`
- A `.meta.json` with `documentId: "1001"` and `version: "0"`
- The global counter has advanced to 1002

### Failure scenarios

**Error: Document number must be 4 digits**

```
Error: Document number must be 4 digits.
```

The documentId must be exactly 4 digits (1000–9999). If you enter `5`, you must pad it to `1005`.

**Error: DocumentId already exists**

```
Error: DocumentId '1001' already exists at docs/strict/1001.md.
```

You need to choose a different number. Check existing documentIds:

```bash
uv run versioned-md doc --info --dir .
```

### Notes

- Strict filenames **must** exactly match the documentId (e.g., `1001.md` not `1001-system-architecture.md`)
- There is no `reference` category support in `doc create` yet — it only accepts `draft` or `strict`
- Reference documents can be placed in `docs/reference/` manually for now (CLI support forthcoming)

---

## SOP 3: Reference Documents (Planned)

> **Note:** The `reference` category is supported in the schema (`docs/reference/` directory) but is not yet exposed in the `doc create` CLI command. This SOP will be expanded once CLI support is added.

### Current approach

Reference documents can be placed manually in `docs/reference/` and then imported using `doc import`, or you can create a `.meta.json` file by hand with the correct fields.

```bash
# Create the file manually
echo "# Glossary

This document defines common terms used in our documentation.

## A

**API** — Application Programming Interface.

" > docs/reference/glossary.md

# Create the companion .meta.json
cat > docs/reference/glossary.meta.json << 'EOF'
{
  "title": "Glossary",
  "description": "Defines common terms used in our documentation",
  "category": "reference",
  "documentId": "glossary",
  "status": "active",
  "version": "0",
  "lastUpdated": "2024-01-15",
  "updatedBy": "jane",
  "reviewer": [],
  "commitHash": "",
  "prNumber": "",
  "version_history": []
}
EOF
```

Reference documents allow descriptive documentIds (not limited to 4 digits) and have lighter governance rules than strict documents.
