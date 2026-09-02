# Reference

Quick-reference material for metadata fields, version history, and troubleshooting common issues.

---

## Reference: Metadata Fields

Each document has a companion `.meta.json` file. All metadata is stored here — Markdown bodies contain no frontmatter.

### Top-Level Fields

| Field | Type | Mutable in PR | CI Managed | Description |
|---|---|---|---|---|
| `title` | string | Yes | No | Display title, appears in documentation navigations |
| `description` | string | Yes | No | Short description for SEO, navigation lists, and search |
| `responsible` | string | Yes | No | GitHub handle of the person who owns this document |
| `category` | string | No | Yes | One of `strict`, `draft`, `retired` — must match parent directory |
| `documentId` | string | No | Yes | 4-digit numeric identifier for strict/draft (e.g. `"1001"`). Descriptive for reference |
| `status` | string | No | Yes | One of `active`, `retired` |
| `version` | string | No | Yes | Current version number as string (e.g. `"1"`, `"42"`) |
| `lastUpdated` | string | No | Yes | Date of last CI-managed update, ISO 8601 (`YYYY-MM-DD`) |
| `updatedBy` | string | No | Yes | GitHub handle of the last person who triggered an update via CI |
| `reviewer` | array | No | Yes | List of GitHub handles who approved the document |
| `commitHash` | string | No | Yes | Short Git SHA of the merge commit that performed the update |
| `prNumber` | string | No | Yes | PR number as a string (e.g. `"42"`) for reference; empty for non-PR commits |

### version_history Array

Nested inside every `.meta.json`:

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | string | Yes | Version number (e.g. `"1"`) |
| `updated_by` | string | Yes | GitHub handle of the updater |
| `last_updated` | string | Yes | Date in `YYYY-MM-DD` format |
| `reviewer` | array | No | List of reviewer handles at the time of update |
| `commit_hash` | string | No | Git SHA of the merge commit |
| `pr_number` | integer | No | PR number, or `null` if not from a PR |
| `action` | string | No | One of: `"created"`, `"updated"`, `"promoted"`, `"imported"` |

### Example .meta.json

```json
{
  "title": "My Document",
  "description": "A description of this document",
  "category": "strict",
  "documentId": "1001",
  "status": "active",
  "version": "2",
  "lastUpdated": "2024-06-15",
  "updatedBy": "jane",
  "reviewer": ["john", "mike"],
  "commitHash": "a1b2c3d",
  "prNumber": "42",
  "version_history": [
    {
      "version": "1",
      "updated_by": "jane",
      "last_updated": "2024-06-01",
      "reviewer": ["john"],
      "commit_hash": "b2c3d4e",
      "pr_number": 40,
      "action": "promoted"
    },
    {
      "version": "2",
      "updated_by": "jane",
      "last_updated": "2024-06-15",
      "reviewer": ["john", "mike"],
      "commit_hash": "a1b2c3d",
      "pr_number": 42,
      "action": "updated"
    }
  ]
}
```

### Mutable vs Protected

**Mutable in PRs** (authors can change these by editing `.meta.json` directly):
- `title` — only if the Markdown body also changed
- `description` — only if the Markdown body also changed
- `responsible` — always allowed

**Protected** (CI only; PRs changing these will be rejected by `check-header.yml`):
- `category`, `documentId`, `status`
- `version`, `lastUpdated`, `updatedBy`
- `reviewer`, `commitHash`, `prNumber`

The CI enforces that top-level `title` and `description` changes only occur when the Markdown body also changes (to prevent trivial metadata-only PRs).

---

## Reference: Version History

The `version_history` array tracks every official change to a document. Each entry is immutable once written by CI.

### Lifecycle of a version_history Entry

A document's version_history progresses through these actions:

1. **`"created"`** — First entry on a new document (not from import)
2. **`"promoted"`** — First entry when a draft is promoted to strict
3. **`"updated"`** — Any subsequent routine update on an existing active document
4. **`"imported"`** — Entry copied from another document's version_history during import

### Importing version_history

When importing a document from another repository, the `version_version_history` from the source is merged into the destination:

- Entries are matched by `version` number
- Conflicting (already-present) versions are skipped
- Imported entries get `action: "imported"` appended
- Use `--skip-history` to disable this entirely

### CI Rules for version_history in PRs

The `check-header.yml` workflow enforces these rules on every PR:

- **No new versions on existing documents** — You cannot add version entries to a document that already has history
- **Existing entries must not change** — The `version` and `updated_by` fields of existing entries must match exactly
- **First PR on a new document is exempt** — If the base branch has no version_history, any history is allowed (this covers imports)

### Example: New Document (First PR)

```json
// Base branch: no version_history, or file doesn't exist yet

// PR branch adds:
"version_history": [
  {
    "version": "1",
    "updated_by": "jane",
    "last_updated": "2024-06-01",
    "action": "created"
  }
]
```

### Example: Existing Document Update

```json
// Base branch has:
"version_history": [
  {
    "version": "1",
    "updated_by": "jane",
    "last_updated": "2024-06-01",
    "action": "created"
  }
]

// PR must NOT change the above entry.
// CI will append:
"version_history": [
  { "version": "1", "updated_by": "jane", "last_updated": "2024-06-01", "action": "created" },
  { "version": "2", "updated_by": "john", "last_updated": "2024-06-10", "action": "updated" }
]
```

---

## Reference: Troubleshooting Checklist

Quick diagnostic reference for the most common errors you will encounter.

### CI Check Fails During PR

| Error Message | Cause | Fix |
|---|---|---|
| `"PR author 'x' is not listed in people.json"` | The person opening the PR is not in `people.json` | Run `versioned-md people import` or `people add --name ... --handle ...` and push to the PR branch |
| `"Approved reviewer 'x' is not listed in people.json"` | Someone who approved the review is not in people.json | Add the missing reviewer first, then re-trigger CI (push a new commit) |
| `"Protected field 'category' changed..."` | Someone edited a protected field in `.meta.json` directly | Revert the `.meta.json` change and let CI handle it on merge |
| `"Category mismatch: ... category='strict' but parent directory is 'drafts'"` | File is in `docs/drafts/` but `.meta.json` says `category: "strict"` | Either move the file to `docs/strict/` or fix the `.meta.json` category field |
| `"strict filename must match documentId exactly..."` | A strict file is named `1001-something.md` instead of `1001.md` | Rename the file to just the documentId (e.g., `1001.md`) |
| `"Duplicate documentId '1001'"` | Two documents have the same documentId | Rename the duplicate or check which documentId should be different |
| `"New version entries added to version_version_history..."` | PR tries to add version_history entries to an existing document | Only the first PR on a new document can add version_history. Subsequent edits should only change the Markdown body |
| `"Missing required field 'version' in version_history"` | The `version_history` entries are missing required fields | Add `version`, `updated_by`, and `last_updated` to each entry |
| `" 'last_updated' must match YYYY-MM-DD"` | Date format in version_history is wrong | Use ISO 8601 format, e.g. `"2024-06-01"` |

### Local CLI Errors

| Error Message | Cause | Fix |
|---|---|---|
| `"people.json not found"` | No `people.json` exists in the repo | Run `versioned-md people add` or `versioned-md people import` |
| `"Document number must be 4 digits"` | Invalid documentId format | Use a 4-digit number (1000–9999) |
| `"Target path already exists"` | Trying to overwrite without `--force` | Use `--force` or remove the existing file first |
| `"Source file not found"` | Path to source document is incorrect | Verify the path exists |
| `"Source file must be a markdown file (.md)"` | Source file has wrong extension | Rename it to `.md` first |
| `"Invalid category 'x'. Must be 'draft' or 'strict'"` | Provided an unsupported category | Only `draft` and `strict` are supported via `doc create`. `reference` is not yet implemented |

### Post-Merge Automation Issues

| Symptom | Cause | Fix |
|---|---|---|
| `update-metadata.yml` does not run on merge | PR was merged with "Squash" or "Rebase" | Re-merge with "Create a merge commit" |
| Metadata was not updated after merge | No `.md` files changed in the merge commit | There is nothing for CI to update |
| `documentId` was not auto-assigned | The document was added via commit but `category` field is missing | Ensure the `.meta.json` has `category` set; run CI or manually set it |
| Duplicate `documentId` after promotion | The draft already had a documentId that collides with an existing strict document | Choose a different documentId or remove the existing one |

### Schema Validation Failures

| Error Message | Cause | Fix |
|---|---|---|
| `"missing required field 'version_history'"` | The `.meta.json` file does not have a `version_history` array | Add `"version_history": []` to the file |
| `" 'version_history' must be an array"` | `version_history` is not a JSON array | Change it to an array: `"version_history": [...]` |
| `" 'category' must be one of 'strict', 'draft', 'retired'"` | Invalid category value | Use one of the three valid values |
| `" schema validation failed: ..."` | Top-level `.meta.json` field fails JSON Schema validation | Check the error message for which field is invalid and correct it |
