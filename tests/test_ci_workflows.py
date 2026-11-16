"""End-to-end tests of the CI workflows shipped to documentation repositories.

Each test drives a generated docs repo through a pull request: branch, commit,
check-header on the PR, approvals, a merge commit on main, and update-metadata.
"""

import pytest


def create_draft(repo, branch: str, title: str, as_user: str = "alice") -> str:
    """Create a draft on a new branch and commit it. Returns the .md path."""
    repo.start_branch(branch)
    result = repo.cli("doc", "create", "--title", title, "--category", "draft", "--description", "A test doc")
    assert result.returncode == 0, result.stderr
    path = repo.git("status", "--porcelain", "--untracked-files=all", "docs/drafts")
    md_paths = [line.split()[-1] for line in path.splitlines() if line.endswith(".md")]
    assert len(md_paths) == 1, path
    repo.commit_all(f"Add {title}", as_user=as_user)
    return md_paths[0]


def merge_new_draft(repo, title: str = "Hello World") -> str:
    """Open, approve and merge a PR adding a draft. Returns the .md path."""
    md_path = create_draft(repo, "add-draft", title)
    number = repo.open_pr("add-draft", "alice")
    repo.approve(number, "bob")
    assert repo.check_pr(number).returncode == 0
    result = repo.merge_pr(number)
    assert result.returncode == 0, result.output
    return md_path


def edit_on_branch(repo, branch: str, md_path: str, text: str = "\nMore content.\n") -> None:
    repo.start_branch(branch)
    with open(repo.path / md_path, "a", encoding="utf-8") as f:
        f.write(text)


# --- check-header (pull_request) -------------------------------------------------------


def test_check_header_passes_for_new_draft(docs_repo):
    create_draft(docs_repo, "add-draft", "Hello World")
    number = docs_repo.open_pr("add-draft", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode == 0, result.output
    assert "check-header PASSED" in result.output


def test_check_header_rejects_pr_author_not_in_people_json(docs_repo):
    create_draft(docs_repo, "add-draft", "Hello World")
    number = docs_repo.open_pr("add-draft", "mallory")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0
    assert "PR author 'mallory' is not listed in people.json" in result.output


def test_check_header_rejects_reviewer_not_in_people_json(docs_repo):
    create_draft(docs_repo, "add-draft", "Hello World")
    number = docs_repo.open_pr("add-draft", "alice")
    docs_repo.approve(number, "mallory")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0
    assert "Approved reviewer 'mallory' is not listed in people.json" in result.output


def test_check_header_rejects_changed_protected_field(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "bump-version", md_path)
    meta = docs_repo.read_meta(md_path)
    meta["version"] = "99"
    docs_repo.write_meta(md_path, meta)
    docs_repo.commit_all("Bump version by hand")
    number = docs_repo.open_pr("bump-version", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0
    assert "'version' changed" in result.output or "Protected field 'version'" in result.output


def test_check_header_rejects_added_history_entry(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "fake-history", md_path)
    meta = docs_repo.read_meta(md_path)
    meta["version_history"].append({"version": "2", "updated_by": "alice", "last_updated": "2026-01-01"})
    docs_repo.write_meta(md_path, meta)
    docs_repo.commit_all("Add a history entry by hand")
    number = docs_repo.open_pr("fake-history", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0
    assert "New version entries added to version_history: 2" in result.output


def test_check_header_rejects_rewritten_history_author(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "rewrite-history", md_path)
    meta = docs_repo.read_meta(md_path)
    meta["version_history"][0]["updated_by"] = "bob"
    docs_repo.write_meta(md_path, meta)
    docs_repo.commit_all("Rewrite history")
    number = docs_repo.open_pr("rewrite-history", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0
    assert "'updated_by' changed" in result.output


def test_check_header_allows_editing_document_body(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "edit-body", md_path)
    docs_repo.commit_all("Edit body")
    number = docs_repo.open_pr("edit-body", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode == 0, result.output


@pytest.mark.xfail(
    strict=True,
    reason="README: all fields of existing history entries are locked; only version and updated_by are checked",
)
def test_check_header_rejects_rewritten_history_date(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "rewrite-date", md_path)
    meta = docs_repo.read_meta(md_path)
    meta["version_history"][0]["last_updated"] = "2000-01-01"
    docs_repo.write_meta(md_path, meta)
    docs_repo.commit_all("Rewrite history date")
    number = docs_repo.open_pr("rewrite-date", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0


@pytest.mark.xfail(strict=True, reason="README: mutable fields may only change together with the body; not checked")
def test_check_header_rejects_title_change_without_body_change(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    docs_repo.start_branch("rename-only")
    meta = docs_repo.read_meta(md_path)
    meta["title"] = "Renamed"
    docs_repo.write_meta(md_path, meta)
    docs_repo.commit_all("Rename only")
    number = docs_repo.open_pr("rename-only", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode != 0


# --- update-metadata (push to main) ----------------------------------------------------


def test_merge_sets_version_and_pr_number(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)

    meta = docs_repo.read_meta(md_path)
    assert meta["version"] == "1"
    assert meta["prNumber"] == "1"
    assert [entry["version"] for entry in meta["version_history"]] == ["1"]
    assert meta["version_history"][0]["pr_number"] == 1
    assert meta["commitHash"] == meta["version_history"][0]["commit_hash"]


def test_merge_pushes_metadata_commit_to_origin(docs_repo, gnu_grep):
    merge_new_draft(docs_repo)

    assert docs_repo.git("log", "-1", "--format=%s").startswith("docs: update")
    assert docs_repo.git("ls-remote", "origin", "main").split()[0] == docs_repo.git("rev-parse", "HEAD")


def test_second_merge_bumps_version(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "edit-body", md_path)
    docs_repo.commit_all("Edit body")
    number = docs_repo.open_pr("edit-body", "alice")
    docs_repo.approve(number, "bob")
    assert docs_repo.check_pr(number).returncode == 0

    result = docs_repo.merge_pr(number)

    assert result.returncode == 0, result.output
    meta = docs_repo.read_meta(md_path)
    assert meta["version"] == "2"
    assert [entry["version"] for entry in meta["version_history"]] == ["1", "2"]


def test_metadata_produced_by_ci_passes_its_own_check(docs_repo, gnu_grep):
    """After CI has written metadata, a normal follow-up PR must still pass check-header."""
    md_path = merge_new_draft(docs_repo)
    edit_on_branch(docs_repo, "follow-up", md_path)
    docs_repo.commit_all("Follow-up edit")
    number = docs_repo.open_pr("follow-up", "alice")

    result = docs_repo.check_pr(number)

    assert result.returncode == 0, result.output


def test_merge_rejects_squash_merge(docs_repo, gnu_grep):
    create_draft(docs_repo, "add-draft", "Hello World")
    number = docs_repo.open_pr("add-draft", "alice")
    docs_repo.git("checkout", "main")
    docs_repo.git("merge", "--squash", "add-draft")
    docs_repo.commit_all(f"Merge pull request #{number} from acme/add-draft (squashed)", as_user="carol")
    # GitHub reports no merge_commit_sha for squash merges in the 'Verify merge method' step

    result = docs_repo.push_to_main()

    assert result.returncode != 0
    assert "only 'Create a merge commit' is allowed" in result.output


def test_direct_push_does_not_run_update_metadata(docs_repo):
    docs_repo.write("notes.txt", "hello\n")
    docs_repo.commit_all("Direct push")

    result = docs_repo.push_to_main()

    assert result.skipped


@pytest.mark.xfail(strict=True, reason="reviewer is taken from .meta.json ([] after doc create), never from the PR")
def test_merge_records_approved_reviewers(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)

    meta = docs_repo.read_meta(md_path)
    assert meta["reviewer"] == ["bob"]
    assert meta["version_history"][0]["reviewer"] == ["bob"]


@pytest.mark.xfail(strict=True, reason="updatedBy is the merge commit's author name, not the PR author's handle")
def test_merge_records_pr_author_handle(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)

    meta = docs_repo.read_meta(md_path)
    assert meta["updatedBy"] == "alice"
    assert meta["version_history"][0]["updated_by"] == "alice"


@pytest.mark.xfail(strict=True, reason="update-metadata treats every changed .md as a document, also outside docs/")
def test_merge_ignores_markdown_outside_docs(docs_repo, gnu_grep):
    docs_repo.start_branch("readme")
    docs_repo.write("README.md", "# Changed readme\n")
    docs_repo.commit_all("Change readme")
    number = docs_repo.open_pr("readme", "alice")

    result = docs_repo.merge_pr(number)

    assert result.returncode == 0, result.output
    assert not (docs_repo.path / "README.meta.json").exists()


@pytest.mark.xfail(strict=True, reason="update-metadata writes a .meta.json for the deleted path of a moved document")
def test_merge_of_retired_document_leaves_no_orphan_meta(docs_repo, gnu_grep):
    md_path = merge_new_draft(docs_repo)
    docs_repo.start_branch("retire")
    result = docs_repo.cli("doc", "retire", "--path", md_path, "--reason", "Obsolete")
    assert result.returncode == 0, result.stderr
    docs_repo.commit_all("Retire")
    number = docs_repo.open_pr("retire", "alice")

    result = docs_repo.merge_pr(number)

    assert result.returncode == 0, result.output
    assert not (docs_repo.path / md_path).with_suffix(".meta.json").exists()
