# CI & Governance

Standard operations for understanding and working with the CI workflows that enforce metadata consistency.

---

## SOP 1: The Pull Request Workflow

**When to use this** — You have made changes to a document and need to push them, get review, and merge them into `main` following the proper governance process.

### Prerequisites

- A `people.json` file exists in the repository
- The PR author is listed in `people.json`
- At least one reviewer is familiar with the document and can review it

### Step 1: Make Your Changes

```bash
# Edit the document (Markdown has no frontmatter — just the body)
docs/drafts/new-feature-guide.md

# If you need to change mutable metadata fields, edit the .meta.json directly:
# - title (mutable)
# - description (mutable)
# - responsible (mutable)
```

### Step 2: Commit and Push

```bash
git add docs/
git commit -m "docs: add new feature guide"
git push origin feature-branch
```

### Step 3: Open a Pull Request

```bash
# If you use the GitHub CLI:
gh pr create \
  --base main \
  --head feature-branch \
  --title "docs: add new feature guide" \
  --body "This PR adds a new feature guide document."
```

Or open the PR through the GitHub web UI.

### Step 4: Get Review

- Request a review from a team member listed in `people.json`
- Reviewers can approve the document, suggest changes, or reject it

### Step 5: Merge (Important: Use "Create a Merge Commit")

When merging, you **must** use **"Create a merge commit"** — not squash or rebase:

```
[ ] Squash and merge
[ ] Rebase and merge
[x] Create a merge commit
```

**Why?** Post-merge automation (`update-metadata.yml`) relies on:

1. The "Merge pull request #123" commit message to extract the PR number
2. A merge commit SHA to record as `commitHash`
3. The merge commit parent to identify changed files

Squash or rebase merges break this automation.

### Step 6: Post-Merge Automation

After merging, the `update-metadata.yml` workflow runs automatically on `main`:

1. Detects the merge commit and extracts the PR number (e.g., `#123`)
2. Fetches approved reviewers from the GitHub API
3. For each changed `.md` file, updates its companion `.meta.json`:
   - Bumps `version` (e.g., `"0"` → `"1"`)
   - Records `lastUpdated` and `updatedBy`
   - Stores `reviewer`, `commitHash`, `prNumber`
   - Appends an entry to `version_history` with `action: "updated"`
4. Auto-commits the updated `.meta.json` files to `main`

You should see a new commit shortly after merge (from the automation bot) updating all affected `.meta.json` files.

### Expected outcome

- Document is in `main` branch
- `.meta.json` updated with `version: "1"` and post-merge metadata
- `version_history` has one entry recording the first official version

### Failure scenarios

**CI check fails: "PR author not in people.json"**

```
check-header FAILED
  - PR author 'unknown-user' is not listed in people.json. Run 'versioned-md people import' to add them.
```

Add the author to `people.json` and push the change, or merge the PR with the `--skip-checks` flag (if your branch protection rules allow it).

**CI check fails: "Reviewer not in people.json"**

```
check-header FAILED
  - Approved reviewer 'external-reviewer' is not listed in people.json.
```

Run `versioned-md people import --dry-run` to see if they'll be discovered. If not, add them manually first.

**CI check fails: "Protected field changed"**

```
check-header FAILED
  - Protected field 'category' changed in .meta.json. From 'draft' to 'strict'. Only CI may modify this field.
```

You or someone edited a protected field in `.meta.json` directly. Let CI handle this — after merging, `update-metadata.yml` will apply the correct values. Edit the Markdown body or mutable fields (`title`, `description`, `responsible`) instead.

**CI check fails: "Category mismatch"**

```
check-header FAILED
  - Category mismatch: docs/drafts/some-doc.meta.json has category='strict' but parent directory is 'drafts' (expected 'draft').
```

The document is in `docs/drafts/` but the metadata says `category: "strict"`. Either move the file to `docs/strict/` or correct the `.meta.json` category field.

### Notes

- Always review the `.meta.json` files that CI auto-commits after merge to ensure they look correct
- If automation fails to commit (rare), you can manually run CI locally via `versioned-md meta validate` to check for errors
- Branch protection should require the `check-header` workflow to pass before merging
