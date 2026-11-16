"""Shared fixtures: a freshly created docs repository and a simulated GitHub around it."""

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from tests.fake_github import FakeGitHub
from tests.workflow_runner import WorkflowResult, run_workflow, runner_env

TESTS_DIR = Path(__file__).parent
WORKFLOWS_DIR = TESTS_DIR.parent / "versioned_md" / "templates" / ".github" / "workflows"
GITHUB_REPOSITORY = "acme/docs"

# handle -> display name. On GitHub, commits made by the merge button carry the display name.
PEOPLE = {
    "alice": "Alice Andersson",
    "bob": "Bob Berg",
    "carol": "Carol Carlsson",
}


def run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, check=False)


def git_env(handle: str) -> dict:
    """Environment that makes git author and commit as the given person."""
    env = dict(os.environ)
    name = PEOPLE.get(handle, handle)
    for role in ("AUTHOR", "COMMITTER"):
        env[f"GIT_{role}_NAME"] = name
        env[f"GIT_{role}_EMAIL"] = f"{handle}@example.com"
    return env


class DocsRepo:
    """A docs repository created by ``versioned-md create``, with a bare ``origin`` and a fake GitHub."""

    def __init__(self, path: Path, github: FakeGitHub, workflow_venv_bin: Path):
        self.path = path
        self.github = github
        self.env = runner_env(workflow_venv_bin, TESTS_DIR / "stubs", github.url)
        self.env["GITHUB_REPOSITORY"] = GITHUB_REPOSITORY
        self._next_pr = 1
        self._prs: dict[int, dict] = {}

    # --- local work -------------------------------------------------------------------

    def git(self, *args: str, as_user: str = "alice") -> str:
        result = run(["git", *args], self.path, git_env(as_user))
        assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stderr}"
        return result.stdout.strip()

    def cli(self, *args: str, as_user: str = "alice") -> subprocess.CompletedProcess:
        """Run ``versioned-md`` inside the repository."""
        return run([sys.executable, "-m", "versioned_md", *args], self.path, git_env(as_user))

    def write(self, rel_path: str, text: str) -> None:
        path = self.path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read_meta(self, rel_path: str) -> dict:
        return json.loads((self.path / rel_path).with_suffix(".meta.json").read_text(encoding="utf-8"))

    def write_meta(self, rel_path: str, meta: dict) -> None:
        self.write(str(Path(rel_path).with_suffix(".meta.json")), json.dumps(meta, indent=2) + "\n")

    def commit_all(self, message: str, as_user: str = "alice") -> None:
        self.git("add", "-A", as_user=as_user)
        self.git("commit", "-m", message, as_user=as_user)

    def start_branch(self, name: str) -> None:
        self.git("checkout", "main")
        self.git("checkout", "-b", name)

    # --- GitHub -----------------------------------------------------------------------

    def open_pr(self, branch: str, author: str) -> int:
        """Open a PR from *branch* into main. Returns its number."""
        number = self._next_pr
        self._next_pr += 1
        self._prs[number] = {
            "branch": branch,
            "author": author,
            "base_sha": self.git("rev-parse", "main"),
            "head_sha": self.git("rev-parse", branch),
        }
        self.github.add_pull(number, author)
        return number

    def approve(self, number: int, reviewer: str) -> None:
        self.github.approve(number, reviewer)

    def check_pr(self, number: int) -> WorkflowResult:
        """Run the check-header workflow, as GitHub does on a pull_request event."""
        pr = self._prs[number]
        context = {
            "github": {
                "repository": GITHUB_REPOSITORY,
                "event": {
                    "pull_request": {
                        "number": number,
                        "base": {"sha": pr["base_sha"]},
                        "head": {"sha": pr["head_sha"]},
                        "user": {"login": pr["author"]},
                    }
                },
            },
            "secrets": {"GITHUB_TOKEN": "fake-token"},
        }
        self.git("checkout", "--detach", pr["head_sha"])
        try:
            return run_workflow(WORKFLOWS_DIR / "check-header.yml", self.path, context, self.env)
        finally:
            self.git("checkout", "main")

    def merge_pr(self, number: int, merged_by: str = "carol") -> WorkflowResult:
        """Merge with a merge commit (GitHub's 'Create a merge commit'), push, run update-metadata."""
        pr = self._prs[number]
        self.git("checkout", "main")
        self.git(
            "merge",
            "--no-ff",
            pr["branch"],
            "-m",
            f"Merge pull request #{number} from {GITHUB_REPOSITORY.split('/')[0]}/{pr['branch']}",
            "-m",
            f"PR {number}",
            as_user=merged_by,
        )
        self.github.pulls[number]["merge_commit_sha"] = self.git("rev-parse", "HEAD")
        self.git("push", "origin", "main")
        return self.push_to_main()

    def push_to_main(self) -> WorkflowResult:
        """Run the update-metadata workflow for the current HEAD of main, as a push event does."""
        context = {
            "github": {
                "repository": GITHUB_REPOSITORY,
                "event": {"head_commit": {"message": self.git("log", "-1", "--format=%B")}},
            },
            "secrets": {"GITHUB_TOKEN": "fake-token"},
        }
        return run_workflow(WORKFLOWS_DIR / "update-metadata.yml", self.path, context, self.env)


@pytest.fixture(scope="session")
def workflow_venv_bin(tmp_path_factory) -> Path:
    """An empty virtualenv standing in for actions/setup-python.

    It deliberately has none of versioned-md's dependencies: the workflow's own
    'Install dependencies' step must install everything the CI scripts need.
    """
    venv_dir = tmp_path_factory.mktemp("workflow-venv")
    venv.create(venv_dir, with_pip=True)
    return venv_dir / "bin"


@pytest.fixture
def github():
    fake = FakeGitHub()
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture
def gnu_grep():
    """The update-metadata workflow uses ``grep -P``, which exists on GitHub's Ubuntu runners but not on macOS."""
    result = subprocess.run(["grep", "-oP", "a", "/dev/null"], capture_output=True, check=False)
    if result.returncode == 2:
        pytest.skip("needs GNU grep like GitHub's Ubuntu runner; run the tests in Docker (see README)")


@pytest.fixture
def docs_repo(tmp_path, github, workflow_venv_bin) -> DocsRepo:
    """A docs repo from ``versioned-md create`` with people.json committed and a bare origin."""
    result = run(
        [
            sys.executable,
            "-m",
            "versioned_md",
            "create",
            "--name",
            "docs",
            "--description",
            "Test docs",
            "--author",
            "Acme",
            "--outdir",
            str(tmp_path),
        ],
        tmp_path,
        git_env("alice"),
    )
    assert result.returncode == 0, result.stderr
    repo = DocsRepo(tmp_path / "docs", github, workflow_venv_bin)

    people = [
        {
            "id": f"p-{handle}",
            "name": name,
            "handle": handle,
            "initials": name[0] + name.split()[1][0],
            "aliases": [],
            "active": True,
        }
        for handle, name in PEOPLE.items()
    ]
    repo.write("people.json", json.dumps({"people": people}, indent=2) + "\n")
    repo.commit_all("Add people")

    origin = tmp_path / "origin.git"
    assert run(["git", "init", "--bare", "-b", "main", str(origin)], tmp_path).returncode == 0
    repo.git("remote", "add", "origin", str(origin))
    repo.git("push", "origin", "main")
    return repo
