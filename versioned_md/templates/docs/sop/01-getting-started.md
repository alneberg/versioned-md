# Getting Started

Standard operations for bootstrapping and configuring a new documentation repository.

---

## SOP 1: Create a New Documentation Repository

**When to use this** — You have a new project that needs managed documentation and want to set up the full versioned-md infrastructure.

### Prerequisites

- Git installed and configured with `user.name` and `user.email`
- Python 3.11+ and `uv` installed
- A GitHub account (for CI workflows)

### Steps

```bash
# Clone or navigate to your workspace
cd ~/projects

# Create a new documentation repository
uv run versioned-md create \
  --name "my-team-docs" \
  --description "Our team's documentation" \
  --author "MyTeam"
```

This creates a new directory `my-team-docs/` with:

```
my-team-docs/
├── docs/
│   ├── strict/
│   ├── drafts/
│   └── reference/
├── .github/
│   ├── workflows/check-header.yml
│   └── workflows/update-metadata.yml
├── .versioned-md.yml
└── pyproject.toml
```

### Interactive mode

Run without flags for an interactive prompt:

```bash
uv run versioned-md create
```

You'll be asked for:

1. Repository name
2. A short description
3. Your name (used as initial author)
4. Organisation override (optional, defaults to your name)

### Expected outcome

- An initialised Git repository with `main` branch
- Directory structure for strict, draft, and reference documents
- CI workflow files ready on the `main` branch
- A `TEMPLATE` branch containing the latest versioned-md templates

### Notes

- Add `--no-git` if you want to manage version control manually
- A `people.json` file is required before creating documents. See **Team Management** for adding your first team member
- The `--org` flag lets you override the organisation name if it differs from the author name

---

## SOP 2: Bootstrap the Repository for First Use

**When to use this** — You have just created a repository and need to populate it with people and your first document before making the first commit.

### Prerequisites

- A repository created with `versioned-md create`
- Git initialised

### Steps

```bash
# 1. Navigate to the repository
cd my-team-docs

# 2. Add at least one person to people.json (required before creating documents)
uv run versioned-md people add \
  --name "Jane Doe" \
  --handle "jane" \
  --initials "JD"

# 3. Optionally add more team members
uv run versioned-md people add \
  --name "John Smith" \
  --handle "john" \
  --initials "JS"

# 4. Create your first draft document
uv run versioned-md doc create \
  --title "Onboarding Guide" \
  --category draft \
  --description "A guide for new team members"

# 5. Commit everything and push
git add .
git commit -m "docs: initial repository setup with onboarding guide"
git push -u origin main
```

### Expected outcome

- A `people.json` file with your team members
- A draft document at `docs/drafts/onboarding-guide.md` with a companion `.meta.json`
- A documentId auto-assigned in `.doc_id_counter.json`
- All changes pushed to the remote

### Notes

- At least one person must exist in `people.json` before documents can be created. The CLI will error otherwise
- Draft documents are auto-named using the title (slugified) and get auto-assigned documentIds
- To create a `strict` document, you must provide a 4-digit documentId — see **Creating Documents**
