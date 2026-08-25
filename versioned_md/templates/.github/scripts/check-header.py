#!/usr/bin/env python3
"""Check that protected frontmatter fields haven't changed in a PR.

For each changed ``*.md`` and ``*.meta.json`` file in the PR:
  - Load frontmatter from base and PR refs.
  - Refuse to allow manual changes to protected keys.
  - Validate that ``category`` matches the parent directory.
  - For strict documents, ensure ``documentId`` is unique across the repo.

Exit code 0 = pass, 1 = fail (print reasons).
"""

import argparse
import sys
from pathlib import Path

# Allow importing from parent directory (scripts/ → lib/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.metadata import (
    diff_frontmatter,
    find_changed_md_refs,
    find_changed_meta_refs,
    get_protected_keys,
    validate_document_id_format,
)


def files_in_ref(ref: str, pattern: str = "*.md") -> list[str]:
    """Return a list of file paths matching *pattern* in a given git ref."""
    import subprocess

    cmd = ["git", "ls-tree", "-r", "--name-only", ref]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = result.stdout.strip().splitlines()
    return [l for l in lines if Path(l).match(pattern)]


def _check_md_file(md_path: Path, base_ref: str, pr_ref: str) -> list[str]:
    """Check a single .md file. Return list of error messages (empty = OK)."""
    errors: list[str] = []

    # Load frontmatter from base and PR refs
    base_text = _git_show(base_ref, str(md_path))
    pr_text = _git_show(pr_ref, str(md_path))

    if pr_text is None:
        return []  # file was deleted in PR

    if base_text is None:
        # New file — nothing to compare against, skip protected checks
        # but validate new-file-specific rules below
        pass

    if base_text is not None:
        base_meta, _ = _parse_frontmatter_from_text(base_text)
        pr_meta, _ = _parse_frontmatter_from_text(pr_text)

        # Check protected keys
        if diff_frontmatter(pr_meta, base_meta, get_protected_keys()):
            errors.append(
                f"Protected metadata changed in {md_path}. "
                f"Only CI should update version, lastUpdated, updatedBy, reviewer, commitHash."
            )
    else:
        pr_meta, _ = _parse_frontmatter_from_text(pr_text)

    # Check category matches parent directory
    category = pr_meta.get("category")
    if category:
        parent_dir = md_path.parent.name
        expected_category = "draft" if parent_dir == "drafts" else parent_dir
        if category != expected_category:
            errors.append(
                f"Category mismatch: {md_path} has category='{category}' "
                f"but parent directory is '{parent_dir}' (expected '{expected_category}')."
            )

    # Validate documentId format
    doc_id = pr_meta.get("documentId")
    if category:
        is_valid, error_msg = validate_document_id_format(doc_id, category)
        if not is_valid:
            errors.append(f"{md_path}: {error_msg}")

    # Validate strict filename matches documentId exactly (no title component)
    if category == "strict" and doc_id:
        expected_name = doc_id
        actual_name = md_path.stem
        if actual_name != expected_name:
            errors.append(
                f"strict filename must match documentId exactly: "
                f"'{md_path}' has stem '{actual_name}', expected '{expected_name}.md'."
            )

    return errors


def _check_meta_file(meta_path: Path, base_ref: str, pr_ref: str) -> list[str]:
    """Check a single .meta.json file. Return list of error messages (empty = OK)."""
    errors: list[str] = []

    base_content = _git_show(base_ref, str(meta_path))
    pr_content = _git_show(pr_ref, str(meta_path))

    if pr_content is None:
        return []

    if base_content is None:
        # New meta file — skip version_history comparison, just ensure it has history
        return []

    base_data = _load_meta_from_text(base_content)
    pr_data = _load_meta_from_text(pr_content)

    # Compare version_history entries
    base_history = {h.get("version", ""): h for h in base_data.get("version_history", [])}
    pr_history = {h.get("version", ""): h for h in pr_data.get("version_history", [])}

    for version, entry in pr_history.items():
        if version in base_history:
            if diff_frontmatter(entry, base_history[version]):
                errors.append(
                    f"version history entry {version} in {meta_path} was modified. "
                    f"Only CI should modify version_history."
                )

    return errors


def _check_strict_uniqueness(md_path: Path, pr_ref: str) -> list[str]:
    """Check that documentId is unique across all strict documents in the PR ref.

    Also checks uniqueness for drafts.
    """
    errors: list[str] = []

    strict_files = files_in_ref(pr_ref, "*.md")
    ids_seen: dict[str, str] = {}  # documentId → file path

    categories_to_check = ("strict", "draft")

    for f in strict_files:
        path = Path(f)
        if path.parent.name not in categories_to_check:
            continue
        text = _git_show(pr_ref, f)
        if text is None:
            continue
        try:
            meta, _ = _parse_frontmatter_from_text(text)
        except ValueError:
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


def _git_show(ref: str, path: str) -> str | None:
    """Run ``git show ref:path`` and return contents, or None if file doesn't exist."""
    import subprocess

    cmd = ["git", "show", f"{ref}:{path}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _parse_frontmatter_from_text(text: str) -> tuple[dict, str]:
    """Minimal frontmatter splitter (mirrors lib.metadata internals)."""
    import re

    import yaml

    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise ValueError("No frontmatter")
    footer = re.search(r"\n---\n", text[4:])
    if not footer:
        raise ValueError("No closing ---")
    header = text[4 : footer.start() + 4]
    body = text[footer.start() + 4 + 4 :]
    try:
        meta = yaml.safe_load(header) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    return meta, body


def _load_meta_from_text(text: str) -> dict:
    """Load a .meta.json file from raw text."""
    import json

    data = json.loads(text)
    if "version_history" not in data:
        data["version_history"] = []
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Check document metadata in a PR")
    parser.add_argument("--base-ref", required=True, help="Base branch commit SHA")
    parser.add_argument("--pr-ref", required=True, help="PR head commit SHA")
    args = parser.parse_args()

    errors: list[str] = []

    # Check changed .md files
    md_files = find_changed_md_refs(args.base_ref, args.pr_ref)
    for mf in md_files:
        path = Path(mf)
        if not path.is_absolute():
            path = Path(".") / path
        file_errors = _check_md_file(path, args.base_ref, args.pr_ref)
        errors.extend(file_errors)

        # Check strict unique documentId
        category = None
        try:
            mf_pr_text = _git_show(args.pr_ref, str(path))
            if mf_pr_text:
                meta, _ = _parse_frontmatter_from_text(mf_pr_text)
                category = meta.get("category")
        except (ValueError, FileNotFoundError):
            pass

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
