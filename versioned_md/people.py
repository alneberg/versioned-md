"""Manage people in a documentation repository."""

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from versioned_md.reviewers import fetch_reviewers

PEOPLE_FILE = Path("people.json")
log = logging.getLogger(__name__)


def _load_people(people_path: Path) -> dict:
    """Load people.json from disk."""
    if not people_path.exists():
        return {"people": []}
    return json.loads(people_path.read_text(encoding="utf-8"))


def _write_people(people_path: Path, data: dict) -> None:
    """Write people.json to disk."""
    people_path.parent.mkdir(parents=True, exist_ok=True)
    people_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _gen_id(name: str) -> str:
    """Generate a deterministic, stable ID from a person's name."""
    slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    slug = re.sub(r"-+", "-", slug).strip("-")
    return f"p-{slug}"


def write_people_file(outdir: Path, name: str, handle: str, initials: str) -> int:
    """Write initial people.json with one person."""
    if not name:
        log.error("Missing person name. Use --person-name.")
        return 1
    if not handle:
        log.error("Missing person handle. Use --person-handle.")
        return 1
    if not initials:
        log.error("Missing person initials. Use --person-initials.")
        return 1

    data = {
        "people": [
            {
                "id": _gen_id(name),
                "name": name,
                "handle": handle,
                "initials": initials,
                "aliases": [],
                "active": True,
            }
        ]
    }
    write_people(outdir / PEOPLE_FILE, data)
    log.info(f"Created {PEOPLE_FILE} with person: {name} ({handle})")
    return 0


def write_people(people_path: Path, data: dict) -> None:
    """Write the people data to disk."""
    _write_people(people_path, data)


def _find_match(people: list[dict], name: str | None, handle: str | None, email: str | None) -> dict | None:
    """Find an existing person matching any known identifier.

    Matches against: handle, email, name, and aliases (all case-insensitive).
    Returns the matching person dict, or None.
    """
    handle = (handle or "").lower()
    email = (email or "").lower()
    name = (name or "").lower()

    for p in people:
        existing = {
            (p.get("handle") or "").lower(),
            (p.get("email") or "").lower(),
            (p.get("name") or "").lower(),
            *(a.lower() for a in (p.get("aliases") or [])),
        }
        existing -= {""}
        if not existing:
            continue

        new_idents = {handle, email, name}
        new_idents -= {""}

        if existing & new_idents:
            return p

    return None


def _merge_to_existing(person: dict, name: str | None, handle: str | None, email: str | None) -> None:
    """Fill in missing fields and add discovered identifiers to aliases."""
    if name and not person.get("name"):
        person["name"] = name
    if handle and not person.get("handle"):
        person["handle"] = handle
    if email and not person.get("email"):
        person["email"] = email

    aliases = set(a.lower() for a in (person.get("aliases") or []))

    # Existing primary identifiers (should not be duplicated in aliases)
    primary = {
        (person.get("handle") or "").lower(),
        (person.get("email") or "").lower(),
        (person.get("name") or "").lower(),
    }
    name_val = person.get("name") or ""
    if name_val:
        primary.add(re.sub(r"[^a-z0-9-]", "", name_val.lower().replace(" ", "-")))

    # Add handle to aliases (the handle itself, and its normalized form)
    if handle:
        h_slug = re.sub(r"[^a-z0-9-]", "", handle.lower())
        for candidate in [handle.lower(), h_slug]:
            if candidate and candidate not in primary and candidate not in aliases:
                aliases.add(candidate)

    # Add email username part to aliases (e.g. "john" from "john@company.com")
    if email:
        user = email.lower().split("@")[0]
        if user and user not in primary and user not in aliases:
            aliases.add(user)

    # Add name variations (if different from existing name)
    if name:
        n_slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
        for candidate in [name.lower(), n_slug]:
            if (
                candidate
                and candidate != (person.get("name") or "").lower()
                and candidate not in primary
                and candidate not in aliases
            ):
                aliases.add(candidate)

    person["aliases"] = sorted(a for a in aliases if a)


def add_person(
    people_path: Path,
    name: str,
    handle: str,
    initials: str,
    aliases: list[str] | None = None,
) -> int:
    """Add a person to people.json."""
    if not name:
        name = _prompt("Name")
    if not handle:
        handle = _prompt("Handle (e.g. github username)")
    if not initials:
        initials = _prompt("Initials (e.g. JD)")

    if not name or not handle or not initials:
        log.error("All fields are required: name, handle, initials.")
        return 1

    data = _load_people(people_path)

    for person in data["people"]:
        if person.get("handle") == handle:
            log.error(f"A person with handle '{handle}' already exists.")
            return 1

    # Build aliases list from --alias flags, excluding handle
    alias_set: set[str] = set(aliases or [])
    for a in alias_set:
        a_lower = a.lower()
        a_slug = re.sub(r"[^a-z0-9-]", "", a_lower)

        # Remove anything that duplicates the handle
        if a_lower == handle.lower() or a_slug == handle.lower():
            alias_set.discard(a_lower)
            alias_set.discard(a_slug)

        # Normalise: always store the slugified form
        alias_set.discard(a_lower)
        alias_set.add(a_slug)

    data["people"].append(
        {
            "id": _gen_id(name),
            "name": name,
            "handle": handle,
            "initials": initials,
            "aliases": sorted(a for a in alias_set if a),
            "active": True,
        },
    )

    _write_people(people_path, data)
    log.info(f"Added person: {name} ({handle})")
    return 0


def deactivate_person(people_path: Path, handle: str) -> int:
    """Deactivate a person by handle."""
    data = _load_people(people_path)

    for person in data["people"]:
        if person.get("handle") == handle:
            if not person.get("active"):
                log.info(f"Person '{handle}' is already inactive.")
                return 0
            person["active"] = False
            _write_people(people_path, data)
            log.info(f"Deactivated person: {person['name']} ({handle})")
            return 0

    log.error(f"No person found with handle '{handle}'.")
    return 1


def list_people(people_path: Path) -> int:
    """List all people in people.json."""
    data = _load_people(people_path)
    people = data.get("people", [])

    if not people:
        log.info("No people registered. Use 'versioned-md people add' to add one.")
        return 0

    for person in people:
        status = "active" if person.get("active") else "inactive"
        aliases_str = ""
        p_aliases = person.get("aliases")
        if p_aliases:
            aliases_str = " [" + ", ".join(p_aliases) + "]"
        print(
            f"  {person['name']:<30} @{person['handle']:<15} {person.get('initials', ''):<5} [{status}]{aliases_str}",
        )

    return 0


def _prompt(message: str, default: str = "") -> str:
    """Interactive prompt helper."""
    if default:
        prompt_str = f"{message} [{default}]: "
    else:
        prompt_str = f"{message}: "
    value = input(prompt_str).strip()
    return value or default


@dataclass
class DiscoveredPerson:
    """A person discovered from git log, GitHub API, or PR reviews."""

    name: str | None
    handle: str
    email: str | None
    source: str  # "github-contributors" | "pr-reviews" | "git-log"
    source_detail: str = ""
    aliases: list[str] | None = None


def _parse_remote_url(remote_url: str) -> tuple[str, str] | None:
    """Extract owner/repo from a git remote URL.

    Handles formats like:
      git@github.com:owner/repo.git
      https://github.com/owner/repo.git
      https://user@github.com/owner/repo.git

    Returns None if the URL does not point to GitHub.
    """
    match = re.search(r"[:/]([^/]+)/([^/.]+?)(?:\.git)?$", remote_url)
    if not match:
        return None
    owner, repo = match.groups()
    return owner, repo


def _is_github_remote(remote_url: str) -> bool:
    return "github.com" in remote_url


def _fetch_contributors(owner: str, repo: str, token: str) -> list[dict]:
    """Fetch all contributors from the GitHub API with pagination."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
    per_page = 100
    contributors = []
    page = 1
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    while True:
        params = {"per_page": per_page, "page": page}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            break
        batch = resp.json()
        if not batch:
            break
        contributors.extend(batch)
        link = resp.headers.get("Link", "")
        if 'rel="next"' not in link:
            break
        page += 1

    return contributors


def _fetch_pr_reviewers(owner: str, repo: str, max_prs: int, token: str) -> list[str]:
    """Fetch approved reviewers from closed PRs, up to max_prs.

    Returns a list of GitHub login strings.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    all_logins: set[str] = set()

    # Fetch closed PRs
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=closed&per_page=100"
    prs: list[dict] = []
    page = 1
    while len(prs) < max_prs:
        params = {"page": page}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            break
        batch = resp.json()
        if not batch:
            break
        prs.extend(batch)
        link = resp.headers.get("Link", "")
        if 'rel="next"' not in link:
            break
        page += 1

    prs = prs[:max_prs]

    for pr in prs:
        pr_number = pr.get("number")
        if not pr_number:
            continue
        reviewers = fetch_reviewers(pr_number, f"{owner}/{repo}", token)
        all_logins.update(reviewers)

    return sorted(all_logins)


def _get_git_log_people(repo_dir: Path) -> list[tuple[str, str]]:
    """Run git log and return unique (author_name, email) pairs.

    Returns an empty list if git is unavailable or the repo has no commits.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--format=%an|||%ae", "--all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    seen: set[str] = set()
    people = []
    for line in result.stdout.strip().splitlines():
        if "|||" not in line:
            continue
        parts = line.split("|||", 1)
        if len(parts) != 2:
            continue
        name, email = parts[0].strip(), parts[1].strip().lower()
        key = (name, email)
        if key in seen:
            continue
        seen.add(key)
        people.append((name, email))
    return people


def _extract_handle_from_email(email: str) -> str | None:
    """Extract a handle from an email address.

    - user@users.noreply.github.com → user
    - user@company.com → user
    """
    local = email.rsplit("@", 1)[0]
    if not local:
        return None
    if "github" in email and "users.noreply" in email:
        # Extract handle from noreply address
        return local
    return local


def _slugify(text: str) -> str:
    """Convert a name to a lowercase dash-separated slug."""
    text = text.lower().replace(" ", "-").replace(".", "").replace("'", "")
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _derive_initials(name: str) -> str:
    """Derive initials from a full name."""
    parts = [p for p in name.replace("-", " ").split() if p]
    return "".join(p[0].upper() for p in parts[:2])


def _resolve_person(name: str | None, email: str | None, source: str) -> tuple[str, str]:
    """Resolve a person's (handle, final_name) from available data.

    Returns (handle, name_used_for_initials).
    """
    handle = None
    name_for_initials = name or "?"

    if source == "github-contributors":
        handle = ""  # caller sets this from login
        pass
    elif source == "pr-reviews":
        handle = ""  # caller sets this from login
        pass
    elif source == "git-log" and email:
        parsed = _extract_handle_from_email(email)
        if parsed:
            handle = parsed
        elif name:
            handle = _extract_handle_from_email(name.lower() + "@example.com") or _slugify(name)
        else:
            handle = "unknown"
    elif source == "git-log" and name:
        handle = _slugify(name)

    if not handle and name:
        handle = _slugify(name)
    elif not handle:
        handle = "unknown"

    return handle, name_for_initials


def import_people(
    repo_dir: Path,
    token: str = "",
    dry_run: bool = False,
    skip_existing: bool = False,
    pr_limit: int = 50,
    from_git: bool = True,
    verbose: bool = False,
    output_dir: Path | None = None,
) -> int:
    """Import people from GitHub API and/or local git log.

    Args:
        repo_dir: Directory used for git operations (scanning authors, remote URL).
        output_dir: Directory where people.json will be written. Defaults to repo_dir.
        token: GitHub personal-access token.
        dry_run: If True, don't write any files.
        skip_existing: If True, skip people already in people.json (checks aliases).
        pr_limit: Max number of PRs to scan for reviewers.
        from_git: If True, include authors from git log.
        verbose: If True, use DEBUG log level.

    Returns:
        0 on success, 1 on error.
    """
    if output_dir is None:
        output_dir = repo_dir

    people_path = output_dir / PEOPLE_FILE
    data = _load_people(people_path) if people_path.exists() else {"people": []}
    existing_people = data.get("people", [])

    github_token = token or os.environ.get("GITHUB_TOKEN", "")
    discovered: dict[str, DiscoveredPerson] = {}  # keyed by handle (lower)

    # Parse remote URL
    remote_result = subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    is_github = False
    owner_repo: tuple[str, str] | None = None
    if remote_result.returncode == 0:
        url = remote_result.stdout.strip()
        if _is_github_remote(url):
            parsed = _parse_remote_url(url)
            if parsed:
                owner_repo = parsed
                is_github = True
                log.info(f"GitHub repository detected: {parsed[0]}/{parsed[1]}")
            else:
                log.warning("Could not parse owner/repo from remote URL.")
        else:
            log.info("Not a GitHub repo — scanning git log only.")

    # Fetch from GitHub contributors API
    if is_github and owner_repo and github_token:
        try:
            contributors = _fetch_contributors(owner_repo[0], owner_repo[1], github_token)
            log.info(f"Fetched {len(contributors)} contributors from GitHub API")
            for c in contributors:
                login = c.get("login", "")
                name = c.get("name") or c.get("login", "")
                email = (c.get("email") or "").lower()
                handle = login
                lower = handle.lower()
                if lower in discovered:
                    continue
                discovered[lower] = DiscoveredPerson(
                    name=name,
                    handle=handle,
                    email=email if email else None,
                    source="github-contributors",
                    source_detail=name,
                )
        except Exception as e:
            log.warning(f"Failed to fetch contributors: {e}")

    # Fetch PR reviewers
    if is_github and owner_repo and github_token:
        try:
            reviewers = _fetch_pr_reviewers(owner_repo[0], owner_repo[1], pr_limit, github_token)
            log.info(f"Fetched {len(reviewers)} reviewers from up to {pr_limit} PRs")
            for login in reviewers:
                lower = login.lower()
                if lower not in discovered:
                    discovered[lower] = DiscoveredPerson(
                        name=None,
                        handle=login,
                        email=None,
                        source="pr-reviews",
                        source_detail="",
                    )
        except Exception as e:
            log.warning(f"Failed to fetch PR reviewers: {e}")

    # Fetch from git log
    if from_git:
        log_people = _get_git_log_people(repo_dir)
        log.info(f"Fetched {len(log_people)} unique authors from git log")
        for name, email in log_people:
            name = name.strip()
            email = email.strip()
            if not name:
                continue

            # Try email first
            if email:
                parsed = _extract_handle_from_email(email)
                if parsed:
                    lower = parsed.lower()
                    if lower not in discovered:
                        discovered[lower] = DiscoveredPerson(
                            name=name,
                            handle=parsed,
                            email=email,
                            source="git-log",
                            source_detail="",
                        )
                    continue

            # Fall back to name-based handle
            handle = _slugify(name) or "unknown"
            lower = handle.lower()
            if lower not in discovered:
                discovered[lower] = DiscoveredPerson(
                    name=name,
                    handle=handle,
                    email=email if email else None,
                    source="git-log",
                    source_detail="",
                )

    if not discovered:
        log.info("No people discovered. Nothing to do.")
        return 0

    # Process: match, merge, or add
    new_people: list[dict] = []
    skip_count = 0
    merge_count = 0
    lines: list[str] = []

    for lower, p in sorted(discovered.items()):
        handle, name = _resolve_person(p.name, p.email, p.source)
        p.handle = handle
        email = p.email or ""
        source_label = {
            "github-contributors": "GitHub contributors",
            "pr-reviews": "PR reviews",
            "git-log": "git log",
        }.get(p.source, p.source)

        match = _find_match(existing_people, name, handle, email)

        if match:
            if skip_existing:
                skip_count += 1
                display_name = name or handle
                lines.append(f"  ⏭ {display_name} — already exists in people.json ({source_label})")
                continue
            _merge_to_existing(match, name, handle, email)
            merge_count += 1
            display_name = name or handle
            lines.append(f"  ↻ {display_name} — merged into existing ({source_label})")
        else:
            if skip_existing:
                skip_count += 1
                display_name = name or handle
                lines.append(f"  ⏭ {display_name} — already exists in people.json ({source_label})")
                continue

            final_name = name or handle or "Unknown"
            initials = _derive_initials(final_name)
            source_detail = ""
            if p.source == "github-contributors" and p.name:
                source_detail = f", name: {p.name}"
            elif p.source == "pr-reviews":
                source_detail = f", handle: {p.handle}"

            lines.append(
                f"  ✔ {final_name} — from {source_label}{source_detail}, initials: {initials}",
            )
            new_people.append(
                {
                    "id": _gen_id(final_name),
                    "name": final_name,
                    "handle": p.handle,
                    "initials": initials,
                    "aliases": [],
                    "active": True,
                },
            )

    prefix_total = f"Discovered {len(discovered)} people from git log, GitHub contributors, and PRs"
    print(prefix_total)
    for line in lines:
        print(line)

    if skip_count:
        print(f"  skipped {skip_count} already in people.json")
    if merge_count:
        print(f"  {merge_count} merged into existing")
    print(f"  {len(new_people)} new person(s) to add")

    if dry_run:
        print("Dry run — no changes written.")
        return 0

    # Write updated people.json
    if new_people:
        data["people"].extend(new_people)

    _write_people(people_path, data)
    if merge_count or new_people:
        msg = []
        if new_people:
            msg.append(f"{len(new_people)} new")
        if merge_count:
            msg.append(f"{merge_count} merged")
        log.info(f"Wrote {', '.join(msg)} to {people_path}")
    else:
        log.info("No new people to add.")

    return 0


def validate_people_path(repo_dir: Path) -> Path:
    """Verify people.json exists in the repo, error if not."""
    people_path = repo_dir / PEOPLE_FILE
    if not people_path.exists():
        log.error(f"{PEOPLE_FILE} not found in {repo_dir}.")
        log.info("Run 'versioned-md people add' to add the first person.")
        sys.exit(1)
    return people_path
