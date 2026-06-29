# Versioned Markdown (versioned-md) Plan

## Overview
A GitHub-based documentation management system for the National Genomics Infrastructure (NGI), Sweden. Manages metadata (version history, reviewers, last-update tracking) via GitHub Actions, with a Python library for reuse across workflows. The markdown docs themselves live in a separate repo. A static HTML output can be produced and hosted flexibly (MkDocs, Starlight, custom server, etc.).

---

## Repository: `versioned-md`

A shared library + template that provides:
- Python helpers (`lib/`) for parsing/updating doc metadata
- GitHub Actions scripts (`.github/scripts/`) for automating metadata management
- GitHub Actions workflows (`.github/workflows/`) for CI/CD automation
- A template doc (MkDocs + Starlight compatible frontmatter)
- A people directory schema (maps GH handles to names/initials)

Each downstream documentation repo gets a fork/clone of this repo for the Actions, and may optionally copy the template, people schema, and serving code.

---

## Metadata Schema

### Frontmatter (in every .md file)
```yaml
---
title: "My Documentation Page"
description: "Short description for nav/SEO"
documentId: "1001"               # 4-digit numeric ID for strict/draft; descriptive for reference
category: reference              # must match parent directory (strict, draft, or reference)
lastUpdated: 2026-06-24          # compatible with Starlight's native lastUpdated
updatedBy: johannes              # GitHub handle of person who triggered last build
reviewer:                        # list of approved reviewers
  - johannes
  - jane
prNumber: "42"                   # PR that was merged (auto-set by CI)
version: "42"                    # sequential version number
commitHash: "a1b2c3d"            # short commit hash of the merge that updated this
---
```

### Document Categories

Documents are organized into three categories by directory, with a `category` field in frontmatter that must match the parent directory:

| Directory | Category | Filename Rules | Special Notes |
|---|---|---|---|
| `docs/strict/` | `strict` | Must be `<documentId>.md` (e.g., `1001.md`) | Full governance, numeric `documentId` |
| `docs/drafts/` | `draft` | Can change freely (descriptive names OK) | Lightweight, transitional, numeric `documentId` |
| `docs/reference/` | `reference` | Can change freely | Independent docs, less strict governance |

Frontmatter `category` field:
```yaml
category: strict   # must match parent directory (strict, draft, or reference)
```

**Compatibility notes:**
- `title` — required by both MkDocs and Starlight
- `description` — used by Starlight for SEO; MkDocs passes through to templates
- `documentId` — stable identifier. For `strict` and `draft` categories: auto-generated 4-digit numeric (from global counter starting at 1001). For `reference` docs: descriptive string allowed.
- `lastUpdated` — matches Starlight's native `lastUpdated`; MkDocs sees as custom key
- All other keys are custom; MkDocs passes through to Jinja templates, Starlight supports via Zod schema extension

### Per-doc metadata companion: `*.meta.json`
```json
{
  "version_history": [
    {
      "version": "1",
      "last_updated": "2026-01-15",
      "updated_by": "alice",
      "reviewer": ["bob"],
      "commit_hash": "abc1234"
    },
    {
      "version": "2",
      "last_updated": "2026-06-24",
      "updated_by": "johannes",
      "reviewer": ["jane", "mike"],
      "commit_hash": "a1b2c3d"
    }
  ]
}
```

- Chronologically oldest first
- Companion file lives alongside the markdown file (e.g., `docs/1001.md` + `docs/1001.meta.json`)
- Python-friendly naming (`snake_case`) for internal processing

---

## Directory Structure

```
versioned-md/
├── lib/
│   ├── __init__.py
│   ├── metadata.py             # Core module: parse, write, diff, load, bump version
│   └── reviewers.py            # GH API: fetch reviewers for a PR
├── .github/
│   ├── scripts/
│   │   ├── check-header.py     # Diff frontmatter/meta.json between PR base and PR head
│   │   └── update-metadata.py  # Fetch reviewers, update frontmatter + meta.json, commit back
│   └── workflows/
│       ├── check-header.yml    # PR trigger: fails if metadata manually changed
│       └── update-metadata.yml # Push-to-main: only on merge commits / promotions
├── template/
│   └── example.md              # Full example with compatible frontmatter
├── people/
│   └── people.json.example     # Schema: name, handle, initials, active
├── pyproject.toml
├── .doc_id_counter.json        # Global doc ID counter (auto-managed by CI, gitignored)
├── .gitignore
└── README.md
```

### Example document repo structure (not in this template repo)

```
my-docs-repo/
├── docs/
│   ├── strict/
│   │   ├── 1001.md
│   │   ├── 1001.meta.json
│   │   ├── 1002.md
│   │   ├── 1002.meta.json
│   │   ├── 1003.md
│   │   └── 1003.meta.json
│   ├── drafts/
│   │   ├── new-module-preview.md        # in-progress, not published
│   │   └── new-module-preview.meta.json
│   └── reference/
│       ├── faq.md
│       ├── faq.meta.json
│       └── glossary.md
│       └── glossary.meta.json
├── people/
│   └── people.json                      # (optional) copied from people/
└── mkdocs.yml                           # (optional) MkDocs config
```

#### Promotion: Draft → Strict

A draft is promoted to strict via a dedicated PR:

1. Author opens PR that changes the document's metadata:
   - Moves file from `docs/drafts/` to `docs/strict/` and renames to `<documentId>.md` (e.g., `1001.md`)
   - Changes `category: draft` to `category: strict` in frontmatter
2. The `documentId` (4-digit numeric) is carried over from the draft — no reassignment needed
3. Check-header enforces:
   - Strict filenames must be `<documentId>.md` with no title component (e.g., `1001.md`, not `1001-system-architecture.md`)
   - `category` field matches parent directory
   - Protected metadata is untouched
4. `update-metadata.yml` on merge:
   - Validates `documentId` uniqueness across all docs (strict + drafts)
   - Validates numeric 4-digit format
   - Writes promotion metadata (`updatedBy`, `lastUpdated`, etc.)
   - Creates first (or next) `version_history` entry in the new `.meta.json`
   - Commits back to main

---

## Files to Create (in dependency order)

### Round 1 (all independent — run 6 in parallel)

**T1:** `lib/__init__.py` + `lib/metadata.py`
- `parse_frontmatter(path) -> dict` — extract YAML frontmatter from `.md`
- `write_frontmatter(path, data)` — write YAML frontmatter to `.md`
- `diff_frontmatter(old, new, protected_keys) -> bool` — compare two frontmatter dicts, return True if protected keys differ
- `load_meta(path) -> dict` — read companion `.meta.json`, return version_history list
- `bump_version(meta_dict) -> str` — increment version from last entry in version_history
- `generate_document_id() -> str` — auto-generate 4-digit doc ID from global counter (starts at 1001)
- `read_next_id() / save_next_id(n)` — read/write the global `.doc_id_counter.json`
- `validate_document_id_format(doc_id, category)` — strict/draft must be 4-digit numeric; reference allows any
- `get_protected_keys() -> [str]` — return list of protected frontmatter keys

**T2:** `lib/reviewers.py`
- `fetch_reviewers(pr_number, repo, token) -> list[str]` — query GH API, return list of login strings from APPROVED reviews

**T7:** `template/example.md`
- Complete example with all frontmatter fields filled in

**T8:** `people/people.json.example`
```json
{
  "people": [
    {
      "name": "Jane Doe",
      "handle": "jane",
      "initials": "JD",
      "active": true
    }
  ]
}
```

**T9:** `pyproject.toml` — update to include `pyyaml`, `requests` as dependencies, configure `lib` as installable package

**T10:** `/.gitignore` — add `.people/`, `__pycache__/`, `.venv/` (check current content first for existing patterns)

### Round 2 (depend on T1 and T2)

**T3:** `.github/scripts/check-header.py`
- CLI script: `--base-ref` (base branch SHA), `--pr-ref` (PR branch SHA), `--file` (path to compare)
- Uses `lib.metadata` to load frontmatter from both refs
- Uses `lib.metadata.diff_frontmatter(old, new, protected_keys)`
- Exits 1 if any protected key changed (exit code signals CI failure)
- Also diffs `.meta.json` files — fails if version_history entries differ
- **Category validation**: verifies `category` in frontmatter matches parent directory
- **Strict + draft ID validation**: verifies `documentId` is 4-digit numeric for strict/draft
- **Uniqueness validation**: for `docs/strict/` and `docs/drafts/`, fails if `documentId` not unique across repo

**T4:** `.github/scripts/update-metadata.py`
- CLI script: uses `--repo`, `--token` (or reads from env)
- Uses `git log --format=%s -1` to get latest commit message; parses `#NNN` PR number
- Calls `lib.reviewers.fetch_reviewers()` via GH API
- Uses `git diff-tree --root --no-commit-id --name-only -r HEAD | grep '\.md$'` to find changed docs
- For each changed `.md`:
  1. `metadata.parse_frontmatter(path)` → current frontmatter
  2. `metadata.load_meta(path)` → version_history
  3. `metadata.bump_version()` → new version number (returns 1 for new doc on promotion)
  4. **Promotion detection**: if path moved from `drafts/` to `strict/` or new `category: strict`, this is a promotion — validate `documentId` uniqueness across repo
  5. Update frontmatter: set `version`, `lastUpdated`, `updatedBy`, `reviewer`, `commitHash`
  6. Write frontmatter back
  7. Add new entry to version_history, write `.meta.json`
- Uses `git add`, `git commit`, `git push` to push updated files back to main

### Round 3 (depend on T3 and T4)

**T5:** `.github/workflows/check-header.yml`
```yaml
name: Check Document Metadata
on:
  pull_request:
    branches: [main]
    paths:
      - 'docs/**/*.md'
      - 'docs/**/*.meta.json'
jobs:
  check-header:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      - name: Install deps
        run: pip install pyyaml requests
      - name: Run check
        run: |
          python .github/scripts/check-header.py
```

**T6:** `.github/workflows/update-metadata.yml`
```yaml
name: Update Document Metadata
on:
  push:
    branches:
      - main
jobs:
  update-metadata:
    if: contains(github.event.head_commit.message, 'Merge pull request') ||
        github.event.commits[0].author.name == 'github-actions[bot]'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # need parent for diff-tree
      - name: Install deps
        run: pip install pyyaml requests
      - name: Update metadata
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python .github/scripts/update-metadata.py
```

---

## Review Process Summary

### Routine edit (existing doc)

1. Author edits body content of an existing `.md` file. **Protected fields and filename cannot change.**
2. `check-header.yml` runs:
    - Fails if `version`, `lastUpdated`, `updatedBy`, `reviewer`, `commitHash`, or `documentId` changed manually in PR
    - Fails if any `.meta.json` version_history entries changed
    - Fails if strict doc filename no longer matches its `documentId`
    - Validates `category` matches parent directory
    - Passes if metadata is untouched (author only edits doc body)
3. Reviewer(s) approve via GitHub UI
4. PR merged (using "Create a merge commit" only)
5. `update-metadata.yml` runs:
   - Reads merge commit → extracts PR number
   - Queries GH API for approved reviewers
   - Reads merge commit author for `updatedBy`
   - Bumps `version` from `.meta.json`
   - Writes new metadata to `.md` frontmatter + `.meta.json`
   - Commits back to main

#### Promotion: Draft → Strict

1. Author moves file from `docs/drafts/` to `docs/strict/`, renames to `<documentId>.md` (e.g., `1001.md`)
2. The existing `documentId` (4-digit numeric) is carried over — no reassignment needed
3. Adds missing fields to frontmatter (`category: strict`, `description`, etc.)
4. Renames the `.meta.json` companion file accordingly (e.g., `1001.meta.json`)
5. `check-header.yml` runs:
    - Validates strict filename matches `documentId` exactly (no title component)
    - Validates metadata is untouched (author can only add/remove fields)
    - Validates `category: strict` matches new path
    - Fails if `documentId` is not unique across the repo
6. Reviewer approves the promotion PR
7. On merge, `update-metadata.yml`:
   - Detects it's a promotion (path changed, category is `strict`)
   - Validates `documentId` uniqueness across all docs in repo
   - Creates first `version_history` entry in the new `.meta.json`
   - Writes promotion metadata (`updatedBy`, `lastUpdated`, `reviewer`, `commitHash`)
   - Commits back to main

---

## Static Output (out of scope for this repo, but the contract is)

A downstream tool (user can choose the framework) would:
1. Scan a `docs/` directory for `.md` files and their companion `.meta.json` files
2. Merge frontmatter fields with `version_history`
3. Produce static HTML with:
   - Title (frontmatter `title`)
   - Metadata bar (author, date, reviewer, version)
   - Version history / changelog (from `.meta.json` version_history)
4. Be deployable anywhere: MkDocs, Starlight, GitHub Pages, S3, Nginx, etc.

The `lib/metadata.py` helpers can be reused by any presentation layer — it's framework-agnostic.

---

## Notes / Tradeoffs Discussed

- **nf-core template sync**: nf-core uses in-repo templates (`pipeline-template/`) + Python tools. No cookiecutter. They regenerate from scratch, diff, and open PRs. Not used as a template system here — only as inspiration for GitHub Actions automation.
- **Single version number** vs semver: Starting with sequential number (1, 2, 3…); major/minor/patch handling TBD
- **`lastUpdated`**: YAML date (2026-06-24) — matches Starlight's native `lastUpdated` field
- **Reviewer source**: Only APPROVED reviews are captured. If multiple reviewers approved, both are stored as list in frontmatter and meta.json
- **Only "merge" strategy** allowed — no squash or rebase merges (they don't produce merge commits, making PR number extraction harder)
- **People directory**: Maps GitHub handles → full names, initials, active status. Lives in `people/people.json`
- **Document categories**: Three directories enforce governance levels. Strict documents require full metadata, unique `documentId`, and promotion PR from drafts.
