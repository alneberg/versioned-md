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
                "name": name,
                "handle": handle,
                "initials": initials,
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


def add_person(people_path: Path, name: str, handle: str, initials: str) -> int:
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

    data["people"].append(
        {
            "name": name,
            "handle": handle,
            "initials": initials,
            "active": True,
        }
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
        print(f"  {person['name']:<30} @{person['handle']:<15} {person.get('initials', ''):<5} [{status}]")

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
) -> int:
    """Import people from GitHub API and/or local git log.

    Returns 0 on success, 1 on error.
    """
    existing: dict[str, dict] = {}
    people_path = repo_dir / PEOPLE_FILE
    if people_path.exists():
        data = _load_people(people_path)
        for person in data.get("people", []):
            existing[person.get("handle", "").lower()] = person

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
                email = c.get("email") or ""
                email = email.lower()
                handle = login
                # Check handle uniqueness
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

    # Build output
    to_add = []
    to_skip = 0
    lines = []

    for lower, person in sorted(discovered.items()):
        if skip_existing and lower in existing:
            to_skip += 1
            lines.append(f"  ⏭ {person.name or person.handle} — already exists in people.json ({person.source})")
            continue

        final_name = person.name or person.handle or "Unknown"
        initials = _derive_initials(final_name)
        person.handle = person.handle or _slugify(final_name) or "unknown"

        source_label = {
            "github-contributors": "GitHub contributors",
            "pr-reviews": "PR reviews",
            "git-log": "git log",
        }.get(person.source, person.source)

        if person.source == "github-contributors" and person.name:
            detail = f", name: {person.name}"
        elif person.source == "pr-reviews":
            detail = ", handle: " + person.handle
        else:
            detail = ""

        lines.append(f"  ✔ {final_name} — from {source_label}{detail}, initials: {initials}")
        to_add.append({"name": final_name, "handle": person.handle, "initials": initials, "active": True})

    prefix_total = f"Discovered {len(discovered)} people from git log, GitHub contributors, and PRs"
    print(prefix_total)
    for line in lines:
        print(line)

    if to_skip:
        print(f"  skipped {to_skip} already existing")
    print(f"  {len(to_add)} new person(s) to add")

    if dry_run:
        print("Dry run — no changes written.")
        return 0

    # Write updated people.json
    if to_add:
        data = _load_people(people_path)
        existing_handles = {p.get("handle", "").lower() for p in data.get("people", [])}

        for person in to_add:
            if person["handle"].lower() not in existing_handles:
                data["people"].append(person)
                existing_handles.add(person["handle"].lower())

        _write_people(people_path, data)
        log.info(f"Wrote {len(to_add)} new person(s) to {people_path}")
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
