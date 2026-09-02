# Maintenance & Administration

Standard operations for keeping the documentation infrastructure up to date, validating metadata, and migrating legacy documents.

---

## SOP 1: Update CI Templates

**When to use this** — A new version of versioned-md has been released and you want to update your repository's CI workflows, Python helpers, and validation scripts to the latest version.

### Prerequisites

- The repository was created with `versioned-md create`
- The `TEMPLATE` branch exists (it is created during bootstrap)
- `GITHUB_TOKEN` is set as an environment variable (for automatic PR creation)

### Steps

```bash
# Navigate to your documentation repository
cd my-team-docs

# Run sync — creates a PR from TEMPLATE -> main
uv run versioned-md sync
```

This command:

1. Compares your current `TEMPLATE` branch with the latest version of embedded templates
2. If changes exist, creates a new commit on the `TEMPLATE` branch
3. Creates a PR from `TEMPLATE` → `main` with the template updates
4. CI runs `check-header.yml` on the PR (verifies your changes don't violate any rules)

### Interactive Output

```
Found 3 updated files:
  .github/workflows/check-header.yml
  .github/workflows/update-metadata.yml
  .github/scripts/check-header.py
Creating pull request TEMPLATE -> main...
Pull request created: https://github.com/your-org/my-docs/pull/5
```

### Step 2: Review the Template Update PR

Open the PR in your browser and review:

- What files changed
- What the actual diffs are
- Whether any changes affect your document workflows

```bash
# View the PR locally
gh pr view 5 --repo your-org/my-docs
```

### Step 3: Merge the Template PR

Once you are satisfied with the changes, merge via GitHub's web UI or:

```bash
gh pr merge 5 --repo your-org/my-docs
```

### Non-Interactive Options

**Create the PR without pushing:**

```bash
uv run versioned-md sync --push false --pr true
```

**Create a PR even if no changes detected** (useful when CI has been modified locally and you want to force the process):

```bash
uv run versioned-md sync --force-pr --push true --pr true
```

**Just update the local TEMPLATE branch without creating a PR:**

```bash
uv run versioned-md sync --push true --pr false
```

### Expected outcome

- A new PR on `main` with the updated template files
- CI passes on the PR
- After merge, your repository uses the latest CI validation scripts and workflows

### Notes

- Template updates are safe to merge — they only affect CI workflows and helper scripts, not your documents
- If you have customised the CI scripts in your repo (which you shouldn't need to), you may want to review the diff carefully
- It is recommended to run `sync` periodically (e.g. quarterly) to stay on the latest validation rules

---

## SOP 2: Validate Metadata

**When to use this** — You are about to merge a large batch of changes and want to ensure all `.meta.json` files are valid before pushing to `main`. Or you received a CI failure and need to debug which files are broken.

### Step 1: Validate All Documents

```bash
# Check every .md file in the repo
uv run versioned-md meta validate --dir .
```

This recursively scans the repository and validates every document's companion `.meta.json` file.

### Step 2: Validate a Specific Document

```bash
# Check a single document
uv run versioned-md meta validate --path docs/strict/1001.meta.json

# Or pass the .md file — it uses the companion .meta.json automatically
uv run versioned-md meta validate --path docs/strict/1001.md
```

### Step 3: Interpret the Output

**All files pass:**

```
  docs/strict/1001.md: OK
  docs/strict/1002.md: OK
  docs/drafts/sample.md: OK
Meta validation passed.
```

**Some files fail:**

```
  docs/strict/1001.md: OK
  docs/strict/1003.md: FAILED
    - 'category' must be one of 'strict', 'draft', 'retired'
    - schema validation failed: must match "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
  docs/drafts/sample.md: OK
make: *** [Makefile:12: meta-check] Error 1
```

Each failure shows:

- The file path that failed
- A list of specific validation errors

### Step 4: Fix Validation Errors

Based on the error messages:

```jsonc
// Example of a failing .meta.json
{
  "title": "My Document",
  "category": "production",     // ERROR: not valid — must be strict/draft/retired
  "documentId": "1003",
  "version_history": [
    {
      "version": "1",
      "updated_by": "jane",
      "last_updated": "01-15-2024"  // ERROR: wrong date format — must be YYYY-MM-DD
    }
  ]
}
```

Fix the issues:

```jsonc
// Corrected
{
  "title": "My Document",
  "category": "draft",  // FIXED: valid category
  "documentId": "1003",
  "version_history": [
    {
      "version": "1",
      "updated_by": "jane",
      "last_updated": "2024-01-15"  // FIXED: correct YYYY-MM-DD format
    }
  ]
}
```

Then re-validate:

```bash
uv run versioned-md meta validate --path docs/strict/1003.md
```

### Steps: Validate as a Pre-Commit Step (optional)

You can add validation to your local Makefile or pre-commit hook:

```bash
# Makefile example
meta-check:
	uv run versioned-md meta validate --dir .
```

### Expected outcome

A clean validation report with all files passing, confirming that CI will also pass.

### Notes

- `meta validate` checks both the JSON schema and business rules (category validity, date formats, required fields)
- It does not check PR-specific rules (e.g. whether protected fields changed between branches) — those are only validated by CI
- Files that have no companion `.meta.json` will report "no companion meta.json found" but are not treated as failures

---

## SOP 3: Migrate a Legacy Repository

**When to use this** — You have an existing documentation repository (possibly with YAML frontmatter, old document structure, or no metadata) and want to modernise it using versioned-md.

### Scenario A: Import Documents from a Different versioned-md Repo

If documents already exist in another versioned-md repository with `.meta.json` files, this is the easiest migration path.

```bash
# Navigate to the target repo
cd new-docs-repo

# Dry run to see what would happen
uv run versioned-md doc import \
  --source /path/to/old-repo/docs/strict/1020-guide.md \
  --category strict \
  --document-id 1020 \
  --dry-run
```

Then perform the import:

```bash
uv run versioned-md doc import \
  --source /path/to/old-repo/docs/strict/1020-guide.md \
  --category strict \
  --document-id 1020

# Import with version_history preserved
uv run versioned-md doc import \
  --source /path/to/old-repo/docs/strict/1020-guide.md \
  --category strict \
  --document-id 1020
# (version_history is merged from source by default)

# Import a batch of documents
for file in /path/to/old-repo/docs/strict/*.md; do
  doc_id=$(basename "$file" .md)
  uv run versioned-md doc import \
    --source "$file" \
    --category strict \
    --document-id "$doc_id"
done
```

### Scenario B: Migrate from a Wiki/Frontmatter Document to versioned-md

If documents have frontmatter (YAML at the top of the file) or no metadata at all, use `doc import` which reads the plain Markdown body.

```bash
# Import a document that has no .meta.json anywhere
uv run versioned-md doc import \
  --source docs/wiki-page.md \
  --category draft

# Check the generated .meta.json
cat docs/drafts/wiki-page.meta.json
```

The result will have sensible defaults:
- `version: "0"` (will be bumped to `"1"` on first CI merge)
- Empty `version_history` (no history to import)
- Auto-assigned documentId for drafts

### Scenario C: Update CI Templates During Migration

If your source repo uses an older version of versioned-md, run `sync` after migration:

```bash
# Update CI to the latest version
uv run versioned-md sync
```

### Expected outcome

- All migrated documents have `.meta.json` companions
- Version history from source documents is preserved (where available)
- The target repo has up-to-date CI workflows

### Notes

- Existing frontmatter in source Markdown files is ignored — versioned-md writes plain Markdown
- If a document already exists in the target repo, use `--force` to overwrite (you'll lose the existing `.meta.json`)
- For bulk migrations, consider writing a small script that iterates over the source documents
- The `--skip-history` flag is useful when importing documents that already exist in the target (to avoid duplicate version entries)
