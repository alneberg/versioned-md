"""Tests of the versioned-md CLI inside a generated docs repository."""

import sys

import pytest

from tests.conftest import git_env, run


def test_new_repository_passes_meta_validate_for_docs(docs_repo):
    for md_path in sorted((docs_repo.path / "docs").rglob("*.md")):
        if md_path.name == "README.md":
            continue
        result = docs_repo.cli("meta", "validate", "--path", str(md_path))
        assert result.returncode == 0, result.stdout


@pytest.mark.xfail(strict=True, reason="meta validate scans every .md in the repo, including README.md and template/")
def test_new_repository_passes_meta_validate(docs_repo):
    result = docs_repo.cli("meta", "validate")

    assert result.returncode == 0, result.stdout


@pytest.mark.xfail(strict=True, reason="people add refuses to run without people.json, which create does not make")
def test_people_add_in_new_repository(tmp_path):
    result = run(
        [
            sys.executable,
            "-m",
            "versioned_md",
            "create",
            "--name",
            "docs",
            "--description",
            "d",
            "--author",
            "Acme",
            "--outdir",
            str(tmp_path),
        ],
        tmp_path,
        git_env("alice"),
    )
    assert result.returncode == 0, result.stderr

    result = run(
        [
            sys.executable,
            "-m",
            "versioned_md",
            "people",
            "add",
            "--name",
            "Alice Andersson",
            "--handle",
            "alice",
            "--initials",
            "AA",
        ],
        tmp_path / "docs",
    )

    assert result.returncode == 0, result.stderr


def test_doc_create_draft_is_valid(docs_repo):
    result = docs_repo.cli("doc", "create", "--title", "Hello World", "--category", "draft", "--description", "x")
    assert result.returncode == 0, result.stderr

    result = docs_repo.cli("meta", "validate", "--path", "docs/drafts/hello-world.md")
    assert result.returncode == 0, result.stdout


def test_doc_promote_draft_to_strict(docs_repo):
    docs_repo.cli("doc", "create", "--title", "Hello World", "--category", "draft", "--description", "x")
    document_id = docs_repo.read_meta("docs/drafts/hello-world.md")["documentId"]

    result = docs_repo.cli("doc", "promote", "--path", "docs/drafts/hello-world.md", "--category", "strict")

    assert result.returncode == 0, result.stderr
    strict_path = f"docs/strict/{document_id}.md"
    assert docs_repo.read_meta(strict_path)["category"] == "strict"
    assert not (docs_repo.path / "docs/drafts/hello-world.md").exists()
    result = docs_repo.cli("meta", "validate", "--path", strict_path)
    assert result.returncode == 0, result.stdout


@pytest.mark.xfail(strict=True, reason="doc retire writes 'retiredReason', which meta-schema.json does not allow")
def test_doc_retire_is_valid(docs_repo):
    docs_repo.cli("doc", "create", "--title", "Hello World", "--category", "draft", "--description", "x")

    result = docs_repo.cli("doc", "retire", "--path", "docs/drafts/hello-world.md", "--reason", "Obsolete")
    assert result.returncode == 0, result.stderr

    result = docs_repo.cli("meta", "validate", "--path", "docs/retired/retired-hello-world.md")
    assert result.returncode == 0, result.stdout


def make_source_repo(tmp_path):
    """A separate git repo with a markdown file edited by two people."""
    source = tmp_path / "source"
    source.mkdir()
    run(["git", "init", "-b", "main"], source)
    (source / "guide.md").write_text("# Guide\n\nFirst version.\n", encoding="utf-8")
    run(["git", "add", "guide.md"], source)
    run(["git", "commit", "-m", "Write guide"], source, git_env("alice"))
    (source / "guide.md").write_text("# Guide\n\nSecond version.\n", encoding="utf-8")
    run(["git", "commit", "-am", "Improve guide"], source, git_env("bob"))
    return source / "guide.md"


@pytest.mark.xfail(strict=True, reason="imported history and originalAuthor/originalDate do not match meta-schema.json")
def test_doc_import_with_git_history_is_valid(docs_repo, tmp_path):
    source = make_source_repo(tmp_path)

    result = docs_repo.cli("doc", "import", "--source", str(source), "--category", "reference")
    assert result.returncode == 0, result.stderr

    result = docs_repo.cli("meta", "validate", "--path", "docs/reference/guide.md")
    assert result.returncode == 0, result.stdout


def test_doc_import_keeps_each_commit_author(docs_repo, tmp_path):
    source = make_source_repo(tmp_path)

    docs_repo.cli("doc", "import", "--source", str(source), "--category", "reference")

    history = docs_repo.read_meta("docs/reference/guide.md")["version_history"]
    assert [(entry["version"], entry["updated_by"]) for entry in history] == [
        ("1", "Alice Andersson"),
        ("2", "Bob Berg"),
    ]
    assert {entry["action"] for entry in history} == {"imported"}


@pytest.mark.xfail(strict=True, reason="--document-id and --dir share the short flag -d")
def test_doc_import_short_flag_for_document_id(docs_repo, tmp_path):
    source = make_source_repo(tmp_path)

    result = docs_repo.cli("doc", "import", "-s", str(source), "-c", "strict", "-d", "1500")

    assert result.returncode == 0, result.stderr
    assert docs_repo.read_meta("docs/strict/1500.md")["documentId"] == "1500"
