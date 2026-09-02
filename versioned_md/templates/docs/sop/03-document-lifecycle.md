# Document Lifecycle

Standard operations for moving documents through their lifecycle: promotion, retirement, and import.

---

## SOP 1: Promote a Draft to Strict

**When to use this** — A draft document is ready for review and needs to be promoted from `docs/drafts/` to `docs/strict/`.

### Prerequisites

- The draft document exists in `docs/drafts/`
- The draft has a companion `.meta.json` file
- If the draft does not yet have a documentId, one will be auto-assigned

### Steps

```bash
# Navigate to the repository
cd my-team-docs

# Promote the document to strict
uv run versioned-md doc promote \
  --path docs/drafts/new-feature-guide.md \
  --category strict
```

This will:

1. Read the companion `.meta.json` from `docs/drafts/new-feature-guide.meta.json`
2. If the draft has no documentId, auto-assign one from the global counter
3. Rename the file to `<documentId>.md` (e.g., `1001.md`)
4. Move it to `docs/strict/`
5. Update the `.meta.json` with the new category and last updated date

### Expected outcome

Before:

```
docs/drafts/
├── new-feature-guide.md
└── new-feature-guide.meta.json
docs/strict/
```

After:

```
docs/drafts/
docs/strict/
├── 1001.md
└── 1001.meta.json
```

The `.meta.json` now has `category: "strict"`.

### What happens on merge

After pushing and merging the PR, the CI automation (`update-metadata.yml`) will:

- Bump the version from `"0"` to `"1"`
- Add a `version_history` entry with `action: "promoted"`
- Record reviewers, commit hash, and PR number

### Failure scenarios

**Error: Document is not in draft category**

```
Error: Cannot promote 'docs/strict/1001.md'. Current category is 'strict' — only 'draft' can be promoted.
```

Strict documents cannot be promoted. If you need to change a strict document's category, edit the `.meta.json` manually (the `category` field is protected on PR but can be changed locally).

**Error: Target path already exists**

```
Error: Target path already exists: docs/strict/1001.md. Remove or rename it first.
```

A file with the same target name already exists. Choose a different documentId or remove the existing file.

**Error: DocumentId already exists**

```
Error: DocumentId '1001' already exists at docs/strict/1001.md.
```

The documentId is taken. The CLI will try to auto-assign the next available number if the source draft has no documentId assigned yet.

### Notes

- The `version_history` from the draft is carried over to the strict version
- If there's no existing `version_history`, CI will create the first entry on the first merge after promotion
- Use `--force` to overwrite the target if it already exists

---

## SOP 2: Retire a Document

**When to use this** — A document is outdated, superseded, or no longer relevant and should be removed from active use while keeping it accessible in `docs/retired/`.

### Prerequisites

- The document exists in `docs/strict/` or `docs/drafts/`
- The document has a companion `.meta.json` file

### Steps

```bash
# Retire a strict document with a reason
uv run versioned-md doc retire \
  --path docs/strict/0999-legacy-system.md \
  --reason "Replaced by 1050-system-v2"
```

This will:

1. Move the file to `docs/retired/retired-0999-legacy-system.md`
2. Update the companion `.meta.json` with `status: "retired"` and the reason

### Interactive mode

Run without flags to be prompted for the path and retirement reason:

```bash
uv run versioned-md doc retire
```

```
Document path (e.g. docs/strict/1001.md): docs/strict/0999-legacy-system.md
Reason for retirement: Replaced by 1050-system-v2
```

### Expected outcome

Before:

```
docs/strict/
├── 0999-legacy-system.md
└── 0999-legacy-system.meta.json
```

After:

```
docs/strict/
docs/retired/
└── retired-0999-legacy-system.md
└── retired-0999-legacy-system.meta.json
```

The `.meta.json` changes:

```jsonc
// Before
{ "status": "active", ... }

// After
{ "status": "retired", "retiredReason": "Replaced by 1050-system-v2", ... }
```

### Failure scenarios

**Error: File already exists at target**

```
Error: File already exists at docs/retired/retired-0999-legacy-system.md
```

A file with that name already exists in `docs/retired/`. Check for duplicate retirement names or rename the source document first.

### Notes

- Retired documents are no longer served in strict or draft — they live in their own directory
- The `status: "retired"` in `.meta.json` prevents the document from passing CI checks for strict/draft
- The `documentId` is preserved — retired documents keep their IDs
- Retired documents can theoretically be restored by moving them back and editing `.meta.json` (no built-in command for this yet)

---

## SOP 3: Import a Document from Elsewhere

**When to use this** — You have an existing Markdown document (from another repository, a wiki, or a colleague) that needs to be brought into the versioned-md structure.

### Prerequisites

- A `people.json` file exists in the repository
- The source file is a valid Markdown file (`.md`)
- Optionally: a companion `.meta.json` file from the source (preserves version history)

### Step 1: Dry Run — Preview What Will Happen

```bash
# Always preview first
uv run versioned-md doc import \
  --source ../old-wiki/pipeline-document.md \
  --category draft \
  --dry-run
```

The output shows:

```
[DRY RUN] Would create: docs/drafts/pipeline-document.md
  category: draft
  documentId: 1001
  [DRY RUN] version_history: 3 entries
```

### Step 2: Import Without Version History (New Document)

```bash
uv run versioned-md doc import \
  --source ../old-wiki/pipeline-document.md \
  --category draft
```

- Creates `docs/drafts/pipeline-document.md` with the source content as the body
- Creates `docs/drafts/pipeline-document.meta.json` with empty `version_history`
- documentId is auto-assigned since no source `.meta.json` exists

### Step 3: Import with Version History (From Another versioned-md Repo)

```bash
# The source has a companion .meta.json with history
uv run versioned-md doc import \
  --source ../other-repo/docs/strict/1020-api-guide.md \
  --category draft
```

- Copies the source markdown body (no frontmatter — Markdown has none in versioned-md)
- Reads `../other-repo/docs/strict/1020-api-guide.meta.json` and copies the title/description
- Merges `version_history` entries from the source, marking them with `action: "imported"`
- Skips entries that already would exist (by version number)

Expected log output:

```
  version_history: 5 entries imported
```

### Step 4: Skip Version History Import

```bash
uv run versioned-md doc import \
  --source ../wiki/guide.md \
  --category draft \
  --skip-history
```

Use this when the source `.meta.json` exists but you don't want to import its version history (e.g., the history would collide with existing versions).

### Step 5: Overwrite or Skip Existing

```bash
# Overwrite if target exists
uv run versioned-md doc import \
  --source another-source.md \
  --category draft \
  --force

# Skip silently if target exists
uv run versioned-md doc import \
  --source another-source.md \
  --category draft \
  --skip-existing

# Quietly exit without writing
uv run versioned-md doc import \
  --source another-source.md \
  --category draft \
  --skip-existing \
  --dry-run
```

### Step 6: Import as Strict

```bash
uv run versioned-md doc import \
  --source ../migration/source.md \
  --category strict \
  --document-id 1030
```

Strict imports require a 4-digit documentId. The source filename doesn't need to match.

### Expected outcome

For a draft import:

```
docs/drafts/
├── pipeline-document.md
└── pipeline-document.meta.json
```

The `.meta.json` contains all top-level fields (`title`, `description`, `category`, `documentId`, `status`, `version`, `lastUpdated`, `updatedBy`, `reviewer`, `commitHash`, `prNumber`, `version_history`).

### Failure scenarios

**Error: Source file not found**

```
Error: Source file not found: docs/missing.md
```

Verify the path is correct and the file exists.

**Error: Source file must be a markdown file (.md)**

```
Error: Source file must be a markdown file (.md): docs/readme.txt
```

The source must be a `.md` file. Rename it first.

**Error: Strict documents require a documentId**

```
Error: Strict documents require a documentId. Provide --document-id.
```

Provide the `--document-id 1030` flag.

**Error: Target already exists**

```
Error: Target already exists: docs/drafts/pipeline-document.md. Use --force to overwrite or --dry-run to preview.
```

Either use `--force` or `--skip-existing` depending on whether you want to replace the file or skip it.

### Notes

- The Markdown body is written as plain text — no frontmatter is generated
- If a source `.meta.json` exists but is invalid JSON, the import continues with empty history and a warning
- The `version_history` merge logic keeps entries that match by version number — no duplicates from the same version
- For the CI to validate after import, remember to commit and push the changes and open a PR
