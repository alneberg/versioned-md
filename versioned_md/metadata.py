"""Core module for parsing, writing, and managing document metadata."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

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
