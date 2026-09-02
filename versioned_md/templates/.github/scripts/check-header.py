#!/usr/bin/env python3
"""Check that protected .meta.json fields haven't changed in a PR.

For each changed ``*.md`` and ``*.meta.json`` file in the PR:
  - Load the companion .meta.json from base and PR refs.
  - Refuse to allow manual changes to protected keys.
  - Validate that ``category`` matches the parent directory.
  - For strict documents, ensure ``documentId`` is unique across the repo.

Exit code 0 = pass, 1 = fail (print reasons).
"""

import argparse
import json
import os
import sys
import re
from pathlib import Path

# Allow importing from parent directory (scripts/ → lib/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.metadata import (
    find_changed_md_refs,
    find_changed_meta_refs,
    get_latest_commit_message,
    get_protected_top_level_keys,
    validate_document_id_format,
    validate_meta_pr,
)
from lib.reviewers import fetch_reviewers


# Protected top-level keys in .meta.json
PROTECTED_KEYS = (
    "category", "documentId", "status",
    "version", "lastUpdated", "updatedBy",
    "reviewer", "commitHash", "prNumber",
)

# Valid categories for documentId
VALID_CATEGORIES = ("strict", "draft")


def files_in_ref(ref: str, pattern: str = "*.md") -> list[str]:
    """Return a list of file paths matching *pattern* in a given git ref."""
    import subprocess

    cmd = ["git", "ls-tree", "-r", "--name-only", ref]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = result.stdout.strip().splitlines()
    return [l for l in lines if Path(l).match(pattern)]


def _load_meta_from_text(text: str) -> dict:
    """Load a .meta.json file from raw text."""
    data = json.loads(text)
    if "version_history" not in data:
        data["version_history"] = []
    return data


def _git_show(ref: str, path: str) -> str | None:
    """Run ``git show ref:path`` and return contents, or None if file doesn't exist."""
    import subprocess

    cmd = ["git", "show", f"{ref}:{path}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _check_md_file(md_path: Path, base_ref: str, pr_ref: str) -> list[str]:
    """Check a single .md file's companion .meta.json. Return list of error messages (empty = OK)."""
    errors: list[str] = []

    pr_meta_path = md_path.with_suffix(".meta.json")
    base_meta_text = _git_show(base_ref, str(pr_meta_path))
    pr_meta_text = _git_show(pr_ref, str(pr_meta_path))

    if pr_meta_text is None and base_meta_text is None:
        return []  # Neither base nor PR has this file

    if pr_meta_text is None:
        return []  # File was deleted/modified in .md but .meta.json was deleted - handled by _check_meta_file

    pr_meta = _load_meta_from_text(pr_meta_text)

    # Validate category matches parent directory
    category = pr_meta.get("category")
    expected_category = "draft" if md_path.parent.name == "drafts" else md_path.parent.name
    if category and category not in ("strict", "draft", "retired"):
        errors.append(
            f"Invalid category '{category}' in {pr_meta_path}. "
            f"Must be 'strict', 'draft', or 'retired'."
        )
    elif category and md_path.parent.name == "drafts" and category != "draft":
        errors.append(
            f"Category mismatch: {pr_meta_path} has category='{category}' "
            f"but parent directory is 'drafts' (expected 'draft')."
        )
    elif category and md_path.parent.name != "drafts" and category not in (md_path.parent.name, "retired"):
        errors.append(
            f"Category mismatch: {pr_meta_path} has category='{category}' "
            f"but parent directory is '{md_path.parent.name}' (expected '{md_path.parent.name}' or 'retired')."
        )

    # Validate documentId format
    doc_id = pr_meta.get("documentId")
    if category:
        is_valid, error_msg = validate_document_id_format(doc_id, category)
        if not is_valid:
            errors.append(f"{pr_meta_path}: {error_msg}")

    # Validate strict filename matches documentId exactly (no title component)
    if category == "strict" and doc_id:
        expected_name = doc_id
        actual_name = md_path.stem
        if actual_name != expected_name:
            errors.append(
                f"strict filename must match documentId exactly: "
                f"'{pr_meta_path}' has stem '{actual_name}', expected '{expected_name}.json'."
            )

    # If base has the file, check protected keys haven't changed
    if base_meta_text is not None:
        base_meta = _load_meta_from_text(base_meta_text)

        # Compare protected top-level fields
        for key in PROTECTED_KEYS:
            base_val = base_meta.get(key)
            pr_val = pr_meta.get(key)
            if base_val is not None and base_val != pr_val:
                errors.append(
                    f"Protected field '{key}' changed in {pr_meta_path}. "
                    f"From '{base_val}' to '{pr_val}'. Only CI may modify protected fields."
                )

        # Validate version_history
        pr_validation_errors = validate_meta_pr(base_meta, pr_meta)
        errors.extend(pr_validation_errors)

    return errors


def _check_meta_file(meta_path: Path, base_ref: str, pr_ref: str) -> list[str]:
    """Check a single .meta.json file. Return list of error messages (empty = OK)."""
    errors: list[str] = []

    base_content = _git_show(base_ref, str(meta_path))
    pr_content = _git_show(pr_ref, str(meta_path))

    if pr_content is None:
        return []

    pr_data = _load_meta_from_text(pr_content)
    meta_errors = _validate_meta_json(pr_data, str(meta_path))
    errors.extend(meta_errors)

    if base_content is not None:
        base_data = _load_meta_from_text(base_content)

        # Check protected top-level fields
        for key in PROTECTED_KEYS:
            base_val = base_data.get(key)
            pr_val = pr_data.get(key)
            if base_val is not None and base_val != pr_val:
                errors.append(
                    f"Protected field '{key}' changed in {meta_path}. "
                    f"Only CI may modify version, category, documentId, "
                    f"lastUpdated, updatedBy, reviewer, commitHash, prNumber, status."
                )

        # Validate version_history
        pr_validation_errors = validate_meta_pr(base_data, pr_data)
        errors.extend(pr_validation_errors)

    return errors


def _validate_meta_json(data: dict, path: str) -> list[str]:
    """Basic meta.json schema validation (no jsonschema dependency in CI)."""
    errors: list[str] = []

    if "version_history" not in data:
        errors.append(f"{path}: missing required field 'version_history'")
        return errors

    history = data.get("version_history", []) or []
    if not isinstance(history, list):
        errors.append(f"{path}: 'version_history' must be an array")
        return errors

    valid_actions = {"created", "updated", "promoted", "imported"}

    for i, entry in enumerate(history):
        if not isinstance(entry, dict):
            errors.append(f"{path}[{i}]: entry must be an object")
            continue

        if "version" not in entry:
            errors.append(f"{path}[{i}]: missing required field 'version'")
        if "updated_by" not in entry:
            errors.append(f"{path}[{i}]: missing required field 'updated_by'")
        if "last_updated" not in entry:
            errors.append(f"{path}[{i}]: missing required field 'last_updated'")
        elif not re.match(r"^\d{4}-\d{2}-\d{2}$", str(entry.get("last_updated", ""))):
            errors.append(f"{path}[{i}]: 'last_updated' must match YYYY-MM-DD")

        action = entry.get("action")
        if action is not None and action not in valid_actions:
            errors.append(
                f"{path}[{i}]: 'action' must be one of {sorted(valid_actions)}, got '{action}'",
            )

    return errors


def _check_strict_uniqueness(md_path: Path, pr_ref: str) -> list[str]:
    """Check that documentId is unique across all strict documents in the PR ref.

    Also checks uniqueness for drafts.
    """
    errors: list[str] = []

    strict_files = files_in_ref(pr_ref, "*.md")
    ids_seen: dict[str, str] = {}  # documentId → file path

    for f in strict_files:
        path = Path(f)
        if path.parent.name not in ("strict", "draft"):
            continue
        meta_path = path.with_suffix(".meta.json")
        text = _git_show(pr_ref, str(meta_path))
        if text is None:
            continue
        try:
            meta = _load_meta_from_text(text)
        except (json.JSONDecodeError, ValueError):
            continue

        doc_id = meta.get("documentId", "")
        if doc_id:
            if doc_id in ids_seen:
                errors.append(
                    f"Duplicate documentId '{doc_id}' in {path} and {ids_seen[doc_id]} — "
                    f"{path.parent.name} documents must have unique documentIds."
                )
            ids_seen[doc_id] = f

    return errors


def _validate_people_in_people_json(
    pr_author: str,
    pr_number: int,
    repo: str,
    base_ref: str,
    token: str,
) -> list[str]:
    """Check that PR author and approved reviewers exist in people.json.

    Returns a list of error messages (empty = OK).
    """
    errors: list[str] = []

    people_text = _git_show(base_ref, "people.json")
    if not people_text:
        errors.append("people.json not found in the base branch. Cannot validate people.")
        return errors

    try:
        people_data = json.loads(people_text)
        people_handles = {p.get("handle", "") for p in people_data.get("people", [])}
    except (json.JSONDecodeError, KeyError):
        errors.append("people.json has invalid structure. Expected { \"people\": [...] }")
        return errors

    if pr_author:
        if pr_author not in people_handles:
            errors.append(
                f"PR author '{pr_author}' is not listed in people.json. "
                f"Run 'versioned-md people import' to add them."
            )

    if repo and token:
        try:
            approved_reviewers = fetch_reviewers(pr_number, repo, token)
            for reviewer in approved_reviewers:
                if reviewer not in people_handles:
                    errors.append(
                        f"Approved reviewer '{reviewer}' is not listed in people.json. "
                        f"Run 'versioned-md people import' to add them."
                    )
        except Exception as e:
            print(f"WARNING: could not fetch reviewers for PR #{pr_number}: {e}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check document metadata in a PR")
    parser.add_argument("--base-ref", required=True, help="Base branch commit SHA")
    parser.add_argument("--pr-ref", required=True, help="PR head commit SHA")
    parser.add_argument("--pr-number", type=int, default=0, help="PR number (for people validation)")
    parser.add_argument("--pr-author", default="", help="PR author login (for people validation)")
    parser.add_argument("--repo", default="", help="Repository in owner/name format")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    errors: list[str] = []

    # Validate PR author and reviewers are in people.json (if PR number provided + token available)
    if args.pr_number and token:
        errors.extend(
            _validate_people_in_people_json(args.pr_author, args.pr_number, args.repo, args.base_ref, token)
        )

    # Also validate people against the merge commit if it's a merge commit
    if args.pr_number and token:
        commit_msg = get_latest_commit_message()
        if "pull request" in commit_msg.lower() or "merge branch" in commit_msg.lower():
            errors.extend(
                _validate_people_in_people_json(args.pr_author, args.pr_number, args.repo, args.base_ref, token)
            )

    # Check changed .md files
    md_files = find_changed_md_refs(args.base_ref, args.pr_ref)
    for mf in md_files:
        path = Path(mf)
        if not path.is_absolute():
            path = Path(".") / path
        file_errors = _check_md_file(path, args.base_ref, args.pr_ref)
        errors.extend(file_errors)

        # Check strict unique documentId
        try:
            mf_pr_text = _git_show(args.pr_ref, str(path.with_suffix(".meta.json")))
            if mf_pr_text:
                meta = _load_meta_from_text(mf_pr_text)
                category = meta.get("category")
        except (json.JSONDecodeError, ValueError):
            category = None

        if category == "strict":
            unique_errors = _check_strict_uniqueness(path, args.pr_ref)
            errors.extend(unique_errors)

    # Check changed .meta.json files
    meta_files = find_changed_meta_refs(args.base_ref, args.pr_ref)
    for mf in meta_files:
        path = Path(mf)
        if not path.is_absolute():
            path = Path(".") / path
        file_errors = _check_meta_file(path, args.base_ref, args.pr_ref)
        errors.extend(file_errors)

    if errors:
        print("check-header FAILED")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("check-header PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
