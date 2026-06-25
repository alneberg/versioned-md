#!/usr/bin/env python3
"""Update document metadata after a merge commit.

Steps for each changed ``*.md`` file:
1. Parse frontmatter + ``*.meta.json``.
2. Determine current state (new promotion, routine update, etc.).
3. Fetch approved reviewers from the GitHub API (using the PR number
   embedded in the merge commit message).
4. Bump version (or initialise it on promotion).
5. Write updated frontmatter and meta.json.
6. Commit and push back to ``main``.

Requires: ``GITHUB_TOKEN`` in env, ``--repo`` as ``owner/name``.
"""

import argparse
import sys
from pathlib import Path

# Allow importing from parent directory (scripts/ → lib/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.metadata import (
    PROTECTED_KEYS,
    bump_version,
    derive_document_id,
    generate_document_id,
    get_commit_author,
    get_commit_date,
    get_latest_commit_message,
    get_latest_commit_sha,
    load_meta,
    parse_frontmatter,
    save_meta,
    write_frontmatter,
    validate_document_id_format,
)
from lib.reviewers import fetch_reviewers


def changed_md_files(base_ref: str, head_ref: str) -> list[str]:
    """Return list of changed ``*.md`` file paths between two refs."""
    import subprocess

    cmd = [
        "git", "diff-tree", "--root", "--no-commit-id",
        "--name-only", "-r", base_ref, head_ref,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    lines = result.stdout.strip().splitlines()
    return [l for l in lines if l.endswith(".md")]


def detect_promotion(md_path: Path, base_meta: dict | None, pr_meta: dict) -> bool:
    """Return True if this file was promoted (moved from drafts/ → strict/)."""
    if base_meta is None:
        # New file — could be a promotion or a new draft
        return False

    old_category = base_meta.get("category", "")
    new_category = pr_meta.get("category", "")

    old_dir = md_path.parent.name
    new_dir = md_path.parent.name  # same path in working tree after merge

    # Promotion: was in drafts, now in strict
    if old_category == "draft" and new_category == "strict":
        return True

    return False


def validate_strict_filename(md_path: Path) -> bool:
    """Return True if the filename matches its documentId for strict docs."""
    path = Path(md_path)
    if path.parent.name != "strict":
        return True
    try:
        meta = parse_frontmatter(path)
    except (ValueError, FileNotFoundError):
        return True
    doc_id = meta.get("documentId")
    if not doc_id:
        return True  # no documentId yet will be assigned by CI
    if path.stem == doc_id:
        return True
    print(f"  VALIDATION ERROR: strict filename '{path}' must be '{doc_id}.md'")
    return False


def validate_strict_filenames(all_md_files: list[str]) -> bool:
    """Validate that all strict docs have filenames matching their documentId."""
    ok = True
    for f in all_md_files:
        path = Path(f)
        if path.parent.name != "strict":
            continue
        if not validate_strict_filename(path):
            ok = False
    return ok


def update_single_file(md_path: str, repo: str, pr_number: int | None, reviewers: list[str]) -> None:
    """Update frontmatter + meta.json for a single document file.

    Args:
        md_path: Relative path to the .md file (from repo root).
        repo: Repository in ``owner/name`` format.
        pr_number: PR number, or None (for non-PR merges).
        reviewers: List of approved reviewer logins.
    """
    path = Path(md_path)

    # Load current frontmatter & metadata
    try:
        meta = parse_frontmatter(path)
    except ValueError:
        print(f"  SKIP {md_path}: no frontmatter found")
        return

    meta_json = load_meta(path)
    version_history = meta_json.get("version_history", []) or []

    # Auto-assign documentId for strict/draft if missing
    category = meta.get("category", "")
    existing_doc_id = meta.get("documentId", "")
    is_strict_or_draft = category in ("strict", "draft")

    if is_strict_or_draft and not existing_doc_id:
        new_id = generate_document_id()
        meta["documentId"] = new_id

    # Check if it's a promotion (old file in drafts → new file in strict)
    # For promotions, base_meta would be None initially
    is_promotion = meta.get("category") == "strict" and not version_history

    if is_promotion:
        print(f"  PROMOTE {md_path}")
    elif is_strict_or_draft and not existing_doc_id:
        print(f"  NEW-DRAFT {md_path} (auto-assigned documentId)")
    else:
        print(f"  UPDATE {md_path}")

    # Derive fields
    commit_sha = get_latest_commit_sha()
    commit_date = get_commit_date()
    author = get_commit_author()

    # Use reviewer list from PR if available; fall back to what's already set
    reviewer_list = meta.get("reviewer")
    if reviewer_list is None and reviewers:
        reviewer_list = reviewers
    elif isinstance(reviewer_list, list):
        reviewer_list = reviewer_list
    elif isinstance(reviewer_list, str):
        reviewer_list = [r.strip() for r in reviewer_list.split(",") if r.strip()]
    else:
        reviewer_list = []

    # Bump version
    new_version = bump_version(meta_json)
    meta_json["version_history"] = version_history

    # Update frontmatter
    meta["version"] = new_version
    meta["lastUpdated"] = commit_date
    meta["updatedBy"] = author
    meta["reviewer"] = reviewer_list
    meta["commitHash"] = commit_sha

    write_frontmatter(path, meta)

    # Build version_history entry
    entry = {
        "version": new_version,
        "last_updated": commit_date,
        "updated_by": author,
        "reviewer": reviewer_list,
        "commit_hash": commit_sha,
    }
    version_history.append(entry)

    save_meta(path, {"version_history": version_history})

    print(f"    version → {new_version}")
    print(f"    updatedBy → {author}")
    print(f"    lastUpdated → {commit_date}")
    print(f"    documentId → {meta.get('documentId', 'N/A')}")
    print(f"    commitHash → {commit_sha}")
    if reviewer_list:
        print(f"    reviewer → {', '.join(reviewer_list)}")


def validate_all_document_ids(all_md_files: list[str]) -> bool:
    """Validate that all strict & draft documents have unique documentIds."""
    ids: dict[str, str] = {}
    ok = True
    for f in all_md_files:
        path = Path(f)
        if path.parent.name not in ("strict", "draft"):
            continue
        try:
            meta = parse_frontmatter(path)
        except (ValueError, FileNotFoundError):
            continue
        doc_id = meta.get("documentId")
        if not doc_id:
            # Will be assigned by CI (e.g., first merge after creation)
            continue
        if doc_id in ids:
            print(f"  VALIDATION ERROR: duplicate documentId '{doc_id}' in {path} and {ids[doc_id]}")
            ok = False
        else:
            ids[doc_id] = str(path)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Update document metadata after merge")
    parser.add_argument("--repo", required=True, help="Repository in owner/name format")
    args = parser.parse_args()

    repo = args.repo
    pr_number = None

    # Step 1: Extract PR number from merge commit message
    commit_msg = get_latest_commit_message()
    from lib.metadata import extract_pr_number_from_commit as epn
    pr_number = epn(commit_msg)

    if pr_number is not None:
        reviewers = fetch_reviewers(pr_number, repo, "")
        print(f"Fetched {len(reviewers)} reviewers for PR #{pr_number}: {reviewers}")
    else:
        reviewers = []
        print(f"No PR number found in commit message: '{commit_msg}'")

    # Step 2: Determine base ref (parent of merge commit)
    import subprocess
    parent_result = subprocess.run(
        ["git", "log", "--format=%P", "-1"],
        capture_output=True, text=True, check=False,
    )
    parents = parent_result.stdout.strip().split()
    base_ref = parents[0] if len(parents) > 1 else ""
    current_sha = get_latest_commit_sha()

    if not base_ref:
        # Could be the very first commit — nothing to update
        print("No parent commit found (likely the initial commit). Skipping update.")
        return 0

    # Step 3: Get list of changed .md files in this merge commit
    md_files = changed_md_files(base_ref, current_sha)

    if not md_files:
        print("No .md files changed in this commit. Skipping update.")
        return 0

    print(f"Found {len(md_files)} changed .md file(s): {md_files}")

    # Step 4: Update each file
    for md_file in md_files:
        update_single_file(md_file, repo, pr_number, reviewers)

    # Step 5: Validate documentId uniqueness across all strict docs
    all_md_files = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    if not validate_all_document_ids(all_md_files):
        print("\nValidation failed — duplicate documentIds found.")
        return 1

    # Step 5b: Validate strict filenames match documentId exactly
    if not validate_strict_filenames(all_md_files):
        print("\nValidation failed — some strict docs have incorrect filenames.")
        print("  Rule: strict docs must be named <documentId>.md (e.g., '1001.md').")
        return 1

    # Step 6: Commit and push
    from lib.metadata import git_add_commit_push as gacp

    print("\nCommitting updates...")
    gacp(
        message=f"docs: update {len(md_files)} document metadata after PR merge",
    )
    print("Done — metadata updated and pushed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
