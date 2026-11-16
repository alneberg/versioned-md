"""Run the shell steps of a GitHub Actions workflow locally, the way a runner would.

Only the subset of GitHub Actions used by the workflows in ``versioned_md/templates/.github/workflows``
is supported:

- ``${{ a.b.c }}`` expressions are replaced by looking up the dotted path in a context dict.
- A job-level ``if:`` may only use ``contains(<path>, '<text>')`` joined with ``||``.
- ``uses:`` steps are skipped: the repository is already checked out, and Python comes from the
  virtualenv that the caller puts first on PATH.
- ``run:`` steps are executed with ``bash -eo pipefail``, like GitHub's default shell.

Anything else raises NotImplementedError, so a workflow change never passes the tests silently.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

EXPRESSION = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
CONTAINS = re.compile(r"^contains\(\s*([\w.]+)\s*,\s*'([^']*)'\s*\)$")


@dataclass
class WorkflowResult:
    skipped: bool
    returncode: int
    output: str


def lookup(context: dict, path: str) -> str:
    """Return the value at a dotted path such as ``github.event.pull_request.number``."""
    value = context
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise NotImplementedError(f"Expression '{path}' is not in the test context")
        value = value[part]
    return str(value)


def substitute(text: str, context: dict) -> str:
    """Replace every ``${{ path }}`` in *text* with its value from *context*."""
    return EXPRESSION.sub(lambda match: lookup(context, match.group(1)), text)


def evaluate_condition(condition: str, context: dict) -> bool:
    """Evaluate a job-level ``if:`` built from ``contains(...)`` calls joined with ``||``."""
    for alternative in condition.split("||"):
        match = CONTAINS.match(alternative.strip())
        if not match:
            raise NotImplementedError(f"Unsupported condition: {alternative.strip()}")
        path, text = match.groups()
        if text in lookup(context, path):
            return True
    return False


def run_workflow(workflow_path: Path, repo_dir: Path, context: dict, env: dict) -> WorkflowResult:
    """Run the single job in *workflow_path* inside *repo_dir*.

    Steps run in order and stop at the first failing step, as on GitHub.
    """
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = list(workflow["jobs"].values())
    if len(jobs) != 1:
        raise NotImplementedError("Only workflows with a single job are supported")
    job = jobs[0]

    if "if" in job and not evaluate_condition(job["if"], context):
        return WorkflowResult(skipped=True, returncode=0, output="")

    output = ""
    for step in job["steps"]:
        if "uses" in step:
            continue
        if "run" not in step:
            raise NotImplementedError(f"Unsupported step: {step}")

        step_env = dict(env)
        for key, value in (step.get("env") or {}).items():
            step_env[key] = substitute(str(value), context)

        script = substitute(step["run"], context)
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
            cwd=repo_dir,
            env=step_env,
            capture_output=True,
            text=True,
            check=False,
        )
        output += f"--- {step.get('name', 'step')}\n{result.stdout}{result.stderr}"
        if result.returncode != 0:
            return WorkflowResult(skipped=False, returncode=result.returncode, output=output)

    return WorkflowResult(skipped=False, returncode=0, output=output)


def runner_env(venv_bin: Path, stub_dir: Path, api_url: str) -> dict:
    """Environment for workflow steps: workflow venv and stubs first on PATH, fake GitHub API."""
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{venv_bin}{os.pathsep}{env['PATH']}"
    env["GITHUB_API_URL"] = api_url
    env.pop("VIRTUAL_ENV", None)
    return env
