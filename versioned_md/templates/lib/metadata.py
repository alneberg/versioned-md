"""Core module for parsing, writing, and managing document metadata."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

log = logging.getLogger(__name__)

SCHEMA_PATH: Path | None = None

try:
    from importlib import resources

    _pkg = resources.files(__package__)
    SCHEMA_PATH = _pkg / "meta-schema.json"
    _schema_bytes = SCHEMA_PATH.read_bytes()
    META_SCHEMA = json.loads(_schema_bytes)
except Exception:
    META_SCHEMA = {"type": "object", "properties": {"version_history": {"type": "array"}}}

FRONTMATTER_DELIMITERS = ("---",)
PROTECTED_KEYS = ("version", "lastUpdated", "updatedBy", "reviewer", "commitHash", "prNumber")
DOCUMENT_KEYS = (
    "title",
    "description",
    "documentId",
    "category",
)


def get_protected_keys() -> list[str]:
    """Return the list of frontmatter keys that CI will not allow to change manually."""
    return list(PROTECTED_KEYS)


def _parse_frontmatter_from_text(text: str) -> tuple[dict[str, Any], str]:
    """Split a file's text into frontmatter dict + body text.

    Raises ValueError if no YAML frontmatter block is found.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise ValueError("No YAML frontmatter found at top of content")

    footer_match = re.search(r"\n---\n", text[4:])
    if not footer_match:
        raise ValueError("Missing closing `---` for YAML frontmatter")

    header_end = text[4 : footer_match.start() + 4]
    body_start = footer_match.start() + 4 + len("---\n")
    body = text[body_start:] if body_start < len(text) else ""

    try:
        meta = yaml.safe_load(header_end) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in frontmatter: {exc}") from exc

    return meta, body


def parse_frontmatter(path: str | Path) -> dict[str, Any]:
    """Extract frontmatter from a `.md` file."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    meta, _ = _parse_frontmatter_from_text(text)
    return meta


def write_frontmatter(path: str | Path, data: dict[str, Any]) -> None:
    """Rewrite frontmatter in an existing `.md` file, preserving the body."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter_from_text(text)
    out = "---\n" + yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n" + body
    p.write_text(out, encoding="utf-8")


def diff_frontmatter(new: dict[str, Any], existing: dict[str, Any], protected_keys: list[str] | None = None) -> bool:
    """Return ``True`` if any protected key changed between the two dicts."""
    if protected_keys is None:
        protected_keys = get_protected_keys()
    for key in protected_keys:
        if key in new and key in existing:
            if new[key] != existing[key]:
                return True
    return False


def load_meta(path: str | Path) -> dict[str, Any]:
    """Read the companion ``*.meta.json`` file for a document.

    Returns a dict with a ``version_history`` list (may be empty).
    Creates the file with an empty list if it does not exist.
    """
    p = Path(path)
    meta_path = p.with_suffix(".meta.json")
    if meta_path.exists():
        txt = meta_path.read_text(encoding="utf-8")
        data = json.loads(txt)
        if "version_history" not in data:
            data["version_history"] = []
        return data
    return {"version_history": []}


def save_meta(path: str | Path, data: dict[str, Any]) -> None:
    """Write a ``*.meta.json`` companion file."""
    p = Path(path)
    meta_path = p.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def bump_version(meta: dict[str, Any]) -> str:
    """Increment the version number based on the latest entry in *meta*["version_history"].

    If the history is empty, returns ``"1"``.
    Returns the new version as a string to preserve format (e.g. ``"42"``).
    """
    history = meta.get("version_history", []) or []
    if not history:
        return "1"
    last = history[-1].get("version", "0")
    # Attempt numeric increment; fall back to string
    try:
        return str(int(last) + 1)
    except ValueError:
        return str(int(last) + 1) if last.isdigit() else last


DOCUMENT_ID_COUNTER_FILE = ".doc_id_counter.json"


def read_next_id() -> int:
    """Read the next document ID from the global counter file.

    Returns the stored value (default 1001).
    The caller is responsible for calling ``save_next_id`` after use.
    """
    counter_path = Path(DOCUMENT_ID_COUNTER_FILE)
    if counter_path.exists():
        txt = counter_path.read_text(encoding="utf-8")
        data = json.loads(txt)
        return int(data.get("next_id", 1001))
    return 1001


def save_next_id(n: int) -> None:
    """Save the next document ID counter to the global counter file."""
    counter_path = Path(DOCUMENT_ID_COUNTER_FILE)
    counter_path.write_text(json.dumps({"next_id": n}, indent=2) + "\n", encoding="utf-8")


def generate_document_id() -> str:
    """Generate a 4-digit document ID and advance the counter by one.

    IDs start at 1001 and increment on each call.
    Returns a zero-padded string like ``"1001"``.
    """
    # Force reload to pick up counter changes
    current = read_next_id()
    save_next_id(current + 1)
    return f"{current:04d}"


def validate_document_id_format(doc_id: str | None, category: str) -> tuple[bool, str]:
    """Validate that a documentId matches the required format for its category.

    Returns ``(is_valid, error_message)``.

    - ``strict`` / ``draft``: must be a 4-digit numeric string (e.g. ``"1001"``)
    - ``reference``: any non-empty string (descriptive is allowed)
    - ``None`` or empty for strict/draft is an error
    """
    if not doc_id or not doc_id.strip():
        if category in ("strict", "draft"):
            return False, f"Category '{category}' requires a 4-digit numeric documentId"
        return True, ""

    if category in ("strict", "draft"):
        if not doc_id.strip().isdigit():
            return False, f"Category '{category}' requires a 4-digit numeric documentId, got '{doc_id}'"
        if not (999 < int(doc_id) < 10000):
            return False, f"Category '{category}' documentId must be 4 digits, got '{doc_id}'"
        return True, ""

    # reference — accept anything
    if not doc_id.strip():
        return False, "documentId must not be empty"
    return True, ""


def derive_document_id(path: str | Path) -> str:
    """Derive a ``documentId`` from a file's name (without extension)."""
    return Path(path).stem


def validate_meta_json(path: str | Path) -> tuple[bool, list[str]]:
    """Validate a meta.json file against the schema.

    Returns (is_valid, list_of_error_messages).
    """
    p = Path(path)
    errors: list[str] = []

    try:
        txt = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, [f"File not found: {p}"]
    except Exception as exc:
        return False, [f"Cannot read {p}: {exc}"]

    try:
        data = json.loads(txt)
    except json.JSONDecodeError as exc:
        return False, [f"Invalid JSON in {p}: {exc}"]

    if not isinstance(data, dict):
        return False, [f"{p}: top-level value must be an object"]

    if "version_history" not in data:
        errors.append(f"{p}: missing required field 'version_history'")
        return False, errors

    if not isinstance(data["version_history"], list):
        errors.append(f"{p}: 'version_history' must be an array")
        return False, errors

    for i, entry in enumerate(data["version_history"]):
        if "version" not in entry:
            errors.append(f"{p}[{i}]: missing required field 'version'")
        elif not isinstance(entry["version"], str):
            errors.append(f"{p}[{i}]: 'version' must be a string")

        if "updated_by" not in entry:
            errors.append(f"{p}[{i}]: missing required field 'updated_by'")
        elif not isinstance(entry["updated_by"], str):
            errors.append(f"{p}[{i}]: 'updated_by' must be a string")

        if "last_updated" not in entry:
            errors.append(f"{p}[{i}]: missing required field 'last_updated'")
        elif not isinstance(entry["last_updated"], str):
            errors.append(f"{p}[{i}]: 'last_updated' must be a string")
        elif not re.match(r"^\d{4}-\d{2}-\d{2}$", str(entry["last_updated"])):
            errors.append(f"{p}[{i}]: 'last_updated' must match YYYY-MM-DD")

        if "action" in entry:
            valid_actions = {"created", "updated", "promoted", "imported"}
            if entry["action"] not in valid_actions:
                errors.append(
                    f"{p}[{i}]: 'action' must be one of {sorted(valid_actions)}, got '{entry['action']}'",
                )

    if errors:
        return False, errors

    try:
        jsonschema.validate(data, META_SCHEMA)
        return True, []
    except jsonschema.ValidationError as exc:
        return False, [f"{p}: schema validation failed: {exc.message}"]


def validate_meta_pr(base_history: list[dict], pr_history: list[dict]) -> list[str]:
    """Validate a PR's version_history against the base branch.

    Rules:
    - No new versions should be added to an existing document.
    - Existing entries must not have modified version or updated_by.
    - First PR on a new document (empty base) allows any history (e.g. imports).

    Returns a list of error messages (empty = OK).
    """
    errors: list[str] = []

    base_by_version = {h.get("version", ""): h for h in base_history if h.get("version")}
    pr_by_version = {h.get("version", ""): h for h in pr_history if h.get("version")}

    # First PR on a new document — allow any history (e.g. imported history)
    if not base_by_version:
        return errors

    # Check for new versions (only allowed when document is new)
    new_versions = set(pr_by_version.keys()) - set(base_by_version.keys())
    if new_versions:
        errors.append(
            f"New version entries added to version_history: {', '.join(sorted(new_versions))}. "
            f"Only version history imports on new documents are allowed.",
        )

    # Compare existing entries on version + updated_by
    for version, base_entry in base_by_version.items():
        pr_entry = pr_by_version.get(version)
        if pr_entry is None:
            continue

        base_ver = base_entry.get("version")
        pr_ver = pr_entry.get("version")
        base_by = base_entry.get("updated_by")
        pr_by = pr_entry.get("updated_by")

        if base_ver and base_ver != pr_ver:
            errors.append(
                f"version_history[{version}]: 'version' changed from '{base_ver}' to '{pr_ver}'. "
                f"Only CI may modify version_history.",
            )
        if base_by and base_by != pr_by:
            errors.append(
                f"version_history[{version}]: 'updated_by' changed from '{base_by}' to '{pr_by}'. "
                f"Only CI may modify version_history.",
            )

    return errors


def validate_category_in_dir(path: str | Path, category: str) -> bool:
    """Return ``True`` if *category* matches the expected parent directory."""
    p = Path(path)
    parent_dir = p.parent.name
    return parent_dir == category


def find_changed_md_refs(base_ref: str, head_ref: str) -> list[str]:
    """Run ``git diff-tree`` and return a list of changed ``*.md`` paths.

    Calls ``git diff-tree --root --no-commit-id --name-only -r <base_ref> <head_ref>``
    and filters to ``.md`` files.
    """
    import subprocess

    cmd = [
        "git",
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        base_ref,
        head_ref,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    lines = result.stdout.strip().splitlines()
    return [x for x in lines if x.endswith(".md")]


def find_changed_meta_refs(base_ref: str, head_ref: str) -> list[str]:
    """Same as :func:`find_changed_md_refs` but for ``*.meta.json`` files."""
    import subprocess

    cmd = [
        "git",
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        base_ref,
        head_ref,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    lines = result.stdout.strip().splitlines()
    return [x for x in lines if x.endswith(".meta.json")]


def extract_pr_number_from_commit(commit_message: str) -> int | None:
    """Parse ``#NNN`` from a merge-commit message.

    Returns ``None`` if no PR number is found.
    Expected format: ``Merge pull request #123 from ...``
    """
    match = re.search(r"#(\d+)", commit_message)
    return int(match.group(1)) if match else None


def get_latest_commit_message() -> str:
    """Return the latest commit's subject line."""
    import subprocess

    result = subprocess.run(
        ["git", "log", "--format=%s", "-1"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def get_latest_commit_sha() -> str:
    """Return the latest commit SHA (short form, 7 chars)."""
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def read_commit_author() -> str:
    """Read the author name/login from the latest commit."""
    import subprocess

    result = subprocess.run(
        ["git", "log", "--format=%an", "-1"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def get_commit_date() -> str:
    """Return the latest commit date (YYYY-MM-DD)."""
    import subprocess

    result = subprocess.run(
        ["git", "log", "--format=%ad", "--date=short", "-1"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def git_add_commit_push(message: str, remote: str | None = None, branch: str | None = None) -> None:
    """Convenience wrapper: ``git add``, ``git commit``, ``git push``."""
    import subprocess

    subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True, text=True)
    if remote is None:
        # Default to upstream or origin
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                check=False,
            )
        upstream = "origin"
    else:
        upstream = remote

    if branch is None:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip()

    subprocess.run(
        ["git", "push", upstream, branch],
        check=False,
        capture_output=True,
        text=True,
    )
