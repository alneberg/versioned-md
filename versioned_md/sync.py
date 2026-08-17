"""Sync TEMPLATE branch with the latest versioned-md template."""

import json
import logging
import os
import re
import tempfile
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

import git

import versioned_md
from versioned_md.create import _normalize_name, render_template

log = logging.getLogger(__name__)


class SyncApplication:
    """Handle syncing a repo's TEMPLATE branch with the latest versioned-md template."""

    def __init__(
        self,
        repo_dir: Path,
        force_pr: bool = False,
        push: bool = True,
        create_pr: bool = True,
    ):
        self.repo_dir = Path(repo_dir)
        self.force_pr = force_pr
        self.push = push
        self.create_pr = create_pr

    def run(self) -> None:
        """Execute the sync process."""
        self._validate_repo()
        context = self._load_config()
        self._checkout_template_branch()
        self._clear_template_branch()
        self._render_template(context)

        repo = git.Repo(self.repo_dir)
        changed = self._has_changes(repo)

        if not changed and not self.force_pr:
            log.info("No changes detected in template -- nothing to sync.")
            return

        self._commit_template_changes(repo)
        if self.push:
            self._push_template_branch()
        if self.create_pr:
            self._create_pull_request()

    def _validate_repo(self) -> None:
        if not self.repo_dir.exists():
            log.error(f"Directory does not exist: {self.repo_dir}")
            raise SystemExit(1)

        try:
            git.Repo(self.repo_dir)
        except git.InvalidGitRepositoryError:
            log.error(f"{self.repo_dir} is not a git repository")
            raise SystemExit(1)

        config_file = self.repo_dir / ".versioned-md.yml"
        if not config_file.exists():
            log.error(f"No .versioned-md.yml found in {self.repo_dir}. Use `versioned-md create` to create a new repo.")
            raise SystemExit(1)

    def _load_config(self) -> dict:
        import yaml

        config_file = self.repo_dir / ".versioned-md.yml"
        config_data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        template_config = config_data.get("template", {})

        context = {
            "name": template_config.get("name", ""),
            "description": template_config.get("description", ""),
            "org": template_config.get("org", ""),
            "author": template_config.get("author", ""),
        }

        ctx_name = context["name"]
        context["repo_name"] = _normalize_name(ctx_name)
        context["short_name"] = _normalize_name(ctx_name)
        context["name_noslash"] = context["repo_name"]
        context["is_nfcore"] = context["org"] == "nf-core"

        return context

    def _checkout_template_branch(self) -> None:
        repo = git.Repo(self.repo_dir)

        if "TEMPLATE" not in repo.branches:
            try:
                repo.remotes.origin.fetch()
            except git.GitCommandError:
                log.warning("Could not fetch from origin, continuing with local state")

        if "TEMPLATE" not in repo.branches:
            repo.git.checkout(["-b", "TEMPLATE"])
            log.info("Created new TEMPLATE branch from main")
        else:
            repo.git.checkout("TEMPLATE")
            log.info("Checked out existing TEMPLATE branch")

    def _clear_template_branch(self) -> None:
        repo = git.Repo(self.repo_dir)

        try:
            tracked_files = repo.git.ls_files().splitlines()
        except git.GitCommandError:
            tracked_files = []

        for f in tracked_files:
            path = self.repo_dir / f
            if path.exists():
                try:
                    path.unlink()
                    log.debug(f"Deleted tracked file: {f}")
                except OSError as e:
                    log.warning(f"Could not delete {f}: {e}")

        # Clean up empty non-hidden directories
        for dirpath, dirnames, filenames in sorted(
            os.walk(self.repo_dir, topdown=False),
        ):
            dir_obj = Path(dirpath)
            if str(dir_obj) == str(self.repo_dir):
                continue
            if dir_obj.name.startswith("."):
                continue
            try:
                if not any(dir_obj.iterdir()):
                    dir_obj.rmdir()
            except OSError:
                pass

    def _render_template(self, context: dict) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            template_dir = Path(versioned_md.__file__).parent / "templates"
            render_template(template_dir, tmp_path, context, force=True)

            for item in tmp_path.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(tmp_path)
                    dest = self.repo_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(item.read_bytes())

    def _has_changes(self, repo: git.Repo) -> bool:
        status = repo.git.status("--porcelain").strip()
        return len(status) > 0

    def _commit_template_changes(self, repo: git.Repo) -> None:
        repo.git.add(A=True)

        if not self._has_changes(repo) and self.force_pr:
            marker = self.repo_dir / ".versioned-md-sync-marker"
            marker.write_text(f"synced at {versioned_md.__version__}\n")
            repo.git.add(str(marker))

        git_message = f"[versioned-md] Template update v{versioned_md.__version__}"
        repo.index.commit(git_message)
        log.info("Committed changes to TEMPLATE branch")

    def _push_template_branch(self) -> None:
        repo = git.Repo(self.repo_dir)
        try:
            repo.git.push("origin", "TEMPLATE")
            log.info("Pushed TEMPLATE branch to origin")
        except git.GitCommandError as e:
            log.warning(f"Could not push TEMPLATE branch: {e}")
            log.info("  git push origin TEMPLATE")

    def _create_pull_request(self) -> None:
        github_token = os.environ.get("GITHUB_TOKEN", "")
        if not github_token:
            log.warning("GITHUB_TOKEN not set -- skipping PR creation")
            log.info("Set GITHUB_TOKEN to create PRs automatically.")
            return

        repo = git.Repo(self.repo_dir)
        try:
            remote_url = repo.remotes.origin.url
            match = re.search(r"[:/]([^/]+)/([^/.]+)(\.git)?$", remote_url)
            if not match:
                log.warning(f"Could not parse owner/repo from remote URL: {remote_url}")
                return
            owner, repo_name = match.groups()
        except Exception as e:
            log.warning(f"Could not determine owner/repo: {e}")
            return

        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"
        pr_data = {
            "title": f"[versioned-md] Template update v{versioned_md.__version__}",
            "body": textwrap.dedent(
                f"""## versioned-md Template Update

A new version of the versioned-md template is available.

**Template version:** {versioned_md.__version__}

**What changed?**
Review the diff between TEMPLATE and main to see what CI
scripts, helpers, or infrastructure files were updated.

**To merge:**
```bash
git checkout main
git merge TEMPLATE
git push origin main
```"""
            ),
            "head": "TEMPLATE",
            "base": "main",
        }

        log.info(f"Creating PR: {owner}/{repo_name} TEMPLATE -> main")

        try:
            data = json.dumps(pr_data).encode("utf-8")
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "Content-Type": "application/json",
                },
            )
            resp = urllib.request.urlopen(req, timeout=30)
            pr_result = json.loads(resp.read().decode("utf-8"))
            pr_url = pr_result.get("html_url", "")
            log.info(f"Pull request created: {pr_url}")
        except Exception as e:
            log.warning(f"Failed to create PR: {e}")
            log.info("You can create the PR manually:")
            log.info("  cd PATH/TO/REPO")
            log.info("  gh pr create --base main --head TEMPLATE")
