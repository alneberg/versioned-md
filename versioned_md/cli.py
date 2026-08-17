#!/usr/bin/env python3
"""CLI entry point for versioned-md."""

import sys
from pathlib import Path

import typer

from versioned_md.create import CreateApplication, InitApplication
from versioned_md.sync import SyncApplication

app = typer.Typer(
    name="versioned-md",
    help="Automated metadata management for markdown documentation repositories.",
    add_completion=False,
)


@app.command("create")
def create(
    name: str = typer.Option(None, "--name", "-n", help="Repository name (e.g. my-docs)."),
    description: str = typer.Option(None, "--description", "-d", help="Short description of the documentation repo."),
    author: str = typer.Option(None, "--author", "-a", help="Organisation or person name."),
    org: str = typer.Option(None, "--org", "-o", help="Organisation / GitHub username."),
    outdir: str = typer.Option(
        None, "--outdir", "-O", help="Directory to create the repo in. Defaults to current dir."
    ),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to a .yml config file with all settings."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing directory if it exists."),
    no_git: bool = typer.Option(
        False,
        "--no-git",
        help="Do not initialise a git repository.",
    ),
):
    """Create a new documentation repository from the versioned-md template.

    Run without arguments for an interactive prompt, or supply flags for non-interactive use.
    """
    # If no args provided and not in TTY, error out
    if not any([name, description, author, org, config]):
        if not sys.stdout.isatty():
            typer.echo(
                "Error: No arguments provided and not running interactively. Provide at least --name.",
                err=True,
            )
            raise typer.Exit(1)

    create_app = CreateApplication(
        name=name or "",
        description=description or "",
        author=author or "",
        org=org or "",
        outdir=outdir or ".",
        config_file=config,
        force=force,
        no_git=no_git,
    )
    # Pass is_interactive based on whether any args were given
    has_args = any([name, description, author, org, config])
    result = create_app.run(is_interactive=not has_args)
    sys.exit(result or 0)


@app.command("init")
def init_repo(
    directory: str = typer.Option(".", "--dir", "-d", help="Directory to initialise (default: current)."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing template branches."),
):
    """Initialise template branches (main, TEMPLATE) on an existing repo.

    Run this on a repository that already has versioned-md infrastructure
    but was created before this tool existed.
    """
    init_app = InitApplication(Path(directory), force=force)
    init_app.run()


@app.command("sync")
def sync(
    directory: str = typer.Option(".", "--dir", "-d", help="Directory to sync (default: current)."),
    force_pr: bool = typer.Option(False, "--force-pr", "-f", help="Create a PR even if no changes."),
    push: bool = typer.Option(True, "--push", help="Push the TEMPLATE branch to remote."),
    create_pr: bool = typer.Option(True, "--pr", help="Create a pull request from TEMPLATE -> main."),
):
    """Sync TEMPLATE branch with the latest versioned-md template.

    Creates a pull request from TEMPLATE -> main so you can review and merge
    template updates. This is the recommended way to update your CI scripts
    and helpers to the latest version.
    """
    sync_app = SyncApplication(
        repo_dir=Path(directory),
        force_pr=force_pr,
        push=push,
        create_pr=create_pr,
    )
    sync_app.run()


if __name__ == "__main__":
    app()
