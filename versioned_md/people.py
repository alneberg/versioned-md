"""Manage people in a documentation repository."""

import json
import sys
from pathlib import Path

from versioned_md.create import log

PEOPLE_FILE = Path("people.json")


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


def validate_people_path(repo_dir: Path) -> Path:
    """Verify people.json exists in the repo, error if not."""
    people_path = repo_dir / PEOPLE_FILE
    if not people_path.exists():
        log.error(f"{PEOPLE_FILE} not found in {repo_dir}.")
        log.info("Run 'versioned-md init . --person-name X --person-handle X --person-initials X' first.")
        sys.exit(1)
    return people_path
