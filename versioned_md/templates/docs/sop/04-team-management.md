# Team Management

Standard operations for managing the people who author and review documentation.

---

## SOP 1: Add a Team Member

**When to use this** — A new person is joining the team and needs to be added to `people.json` before they can author or review documents.

### Prerequisites

- A `people.json` file exists in the repository
- You have the person's full name, GitHub handle, and initials

### Steps: Non-Interactive

```bash
# Add a person via command-line flags
uv run versioned-md people add \
  --name "Jane Doe" \
  --handle "jane" \
  --initials "JD"
```

This adds an entry to `people.json`:

```json
{
  "id": "p-jane-doe",
  "name": "Jane Doe",
  "handle": "jane",
  "initials": "JD",
  "aliases": [],
  "active": true
}
```

### Steps: Interactive

```bash
uv run versioned-md people add
```

You'll be prompted for:

```
Name: Jane Doe
Handle (e.g. github username): jane
Initials (e.g. JD): JD
```

### Adding Aliases

A person may be known by multiple GitHub handles or names. Add them with `--alias`:

```bash
uv run versioned-md people add \
  --name "Jane Doe" \
  --handle "jane" \
  --initials "JD" \
  --alias "janed" \
  --alias "j.doe"
```

Aliases are stored as a list alongside the primary handle. When matching people during imports, aliases are checked as well.

### Expected outcome

The `people.json` file grows by one entry. The `name` field must be unique (case-insensitive). If a duplicate is detected, the import or add will fail.

### Failure scenarios

**Error: Person has already been added**

```
Error: Person with name 'Jane Doe' already exists in people.json.
```

The person's name already exists. Use `--alias` to add an extra handle instead, or check the existing entry.

**Error: Handle already in use**

```
Error: Handle 'jane' already in use by 'Jane Smith'.
```

Two people cannot share the same GitHub handle. Update the existing person's entry or choose a different handle.

### Notes

- You must have at least one person in `people.json` before creating any documents
- CI checks will fail if a PR author or approved reviewer is not found in `people.json`
- Use **Team Import** (SOP 2 below) to bulk-add people instead of adding them one by one
- The `id` field (`p-jane-doe`) is auto-generated from the name and should not be edited manually

---

## SOP 2: Bulk Import People from GitHub

**When to use this** — You have a repo with a history of contributors, PR reviewers, and committers, and want to populate `people.json` automatically rather than adding each person manually.

### Prerequisites

- A `people.json` file exists (even an empty `{"people": []}` is fine)
- A GitHub personal-access token with `repo` and `read:user` scopes
- The token set as the `GITHUB_TOKEN` environment variable, or passed via `--token`

### Step 1: Dry Run — Preview Who Will Be Discovered

```bash
uv run versioned-md people import \
  --dry-run \
  --token "$GITHUB_TOKEN" \
  --pr-limit 50
```

This scans:

1. **Git log** — all authors across all branches
2. **GitHub contributors API** — users who have pushed commits
3. **GitHub PR review API** — users who have approved PRs (up to last 50, controlled by `--pr-limit`)

Output example:

```
Importing people...
  Scanning git log: found 8 unique authors
  Scanning GitHub contributors: found 12 unique users
  Scanning PR reviewers (last 50): found 5 unique reviewers
  Total unique contributors found: 15
  New: 7
  Merged into existing: 4
  Already in people.json: 4
```

### Step 2: Run the Import

```bash
uv run versioned-md people import \
  --token "$GITHUB_TOKEN" \
  --pr-limit 50
```

This writes the discovered people to `people.json`.

### Step 3: Verify and Clean Up

```bash
cat people.json
```

Check for:

- People whose GitHub handle looks wrong (e.g. a bot or a system account)
- People who have left the organisation (mark them with `active: false` — see **Team Management SOP**)
- Duplicates that weren't merged correctly (may need manual fix)

### Optional: Skip Git Log

If you only want to import from GitHub (not local git log):

```bash
uv run versioned-md people import \
  --token "$GITHUB_TOKEN" \
  --no-git
```

### Optional: Skip Existing

If you want to ONLY add new people and leave existing entries untouched:

```bash
uv run versioned-md people import \
  --token "$GITHUB_TOKEN" \
  --skip-existing
```

### Optional: Output to a Different Directory

```bash
uv run versioned-md people import \
  --output-dir /tmp/ \
  --dry-run
```

This writes to `/tmp/people.json` instead of the current directory. Useful for reviewing before overwriting.

### Expected outcome

An updated `people.json`:

```json
{
  "people": [
    {
      "id": "p-jane-doe",
      "name": "Jane Doe",
      "handle": "jane",
      "initials": "JD",
      "aliases": ["janed", "j.doe"],
      "active": true
    },
    {
      "id": "p-john-smith",
      "name": "John Smith",
      "handle": "john",
      "initials": "JS",
      "aliases": [
        "jsmith",
        "john.smith"
      ],
      "active": true
    }
  ]
}
```

### Failure scenarios

**Error: GitHub API rate limit exceeded**

```
Rate limit exceeded. Please check your token and try again.
```

Verify `GITHUB_TOKEN` is set and has the correct scopes. A token with `repo` scope has higher rate limits than anonymous requests.

**Error: Not a GitHub repo**

```
No GitHub remote found. Falling back to git log only.
```

Your repo doesn't have a GitHub remote. The import will still work — it scans git log authors — but won't try to discover PR reviewers.

### Notes

- People are matched by name, handle, email, and aliases — if any field overlaps, the import merges new aliases into the existing entry
- Initials are auto-generated from the full name if not provided (e.g., "Jane Doe" → "JD")
- The email address from git log is added as an alias, not as a separate field
- If a person's GitHub handle contains a hyphen that doesn't match the git log username, aliases help bridge the gap
- Consider running `--dry-run` first to see who will be added before overwriting

---

## SOP 3: Deactivate a Team Member

**When to use this** — A team member is leaving, going on leave, or no longer involved with documentation, and you want to prevent them from appearing as valid authors/reviewers.

### Prerequisites

- The person has an existing entry in `people.json`

### Steps

```bash
# Deactivate a team member
uv run versioned-md people deactivate \
  --handle "jane"
```

This sets the person's entry to `active: false` in `people.json` without removing them:

```json
{
  "id": "p-jane-doe",
  "name": "Jane Doe",
  "handle": "jane",
  "initials": "JD",
  "aliases": [],
  "active": false
}
```

### Expected outcome

- The person's `active` field is set to `false`
- Their entry remains in `people.json` — their historical contributions (commits, version history) remain intact
- Future PR checks will not match deactivated people as valid authors or reviewers

### Failure scenarios

**Error: Handle not found**

```
Error: Handle 'jane' not found in people.json.
```

The handle doesn't exist. Check existing handles:

```bash
cat people.json | grep '"handle"'
```

### Notes

- Deactivating does not delete any document metadata — existing documents still have `updatedBy`, `reviewer`, and `version_history` entries referencing the deactivated person
- To restore someone, manually edit `people.json` and set `"active": true`, or add the person again with `people add` (which will match and activate their entry)
- Consider keeping deactivated people in the file for historical accuracy rather than deleting them entirely
