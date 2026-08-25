#!/usr/bin/env python3
"""CLI entry point for versioned-md."""

import os
import sys
from pathlib import Path

import typer

from versioned_md.create import CreateApplication, InitApplication
from versioned_md.doc import DocCreate, DocPromote, DocRetire
from versioned_md.people import add_person, deactivate_person, validate_people_path
from versioned_md.sync import SyncApplication

app = typer.Typer(
    name="versioned-md",
    help="Automated metadata management for markdown documentation repositories.",
    add_completion=False,
)

doc_app = typer.Typer()
people_app = typer.Typer()

app.add_typer(doc_app, name="doc", help="Manage documents locally.")
app.add_typer(people_app, name="people", help="Manage team members in people.json.")


@doc_app.command("create")
def doc_create(
    title: str = typer.Option("", "--title", "-t", help="Document title."),
    description: str = typer.Option("", "--description", "-d", help="Document description."),
    category: str = typer.Option("", "--category", "-c", help="Document category (draft or strict)."),
    directory: str = typer.Option(".", "--dir", help="Repository directory (default: current)."),
):
    """Create a new document with frontmatter.

    You'll be prompted for the missing information.
    """
    repo_dir = Path(directory)
    if not repo_dir.exists():
        typer.echo(f"Error: Directory '{directory}' not found.", err=True)
        sys.exit(1)
    has_args = bool(title or category)
    is_tty = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())
    interactive = not has_args and is_tty
    doc_create = DocCreate(title=title, category=category, description=description, interactive=interactive)
    result = doc_create.run(repo_dir)
    sys.exit(result or 0)


@doc_app.command("promote")
def doc_promote(
    path: str = typer.Option("", "--path", "-p", help="Document path to promote (e.g. docs/drafts/my-doc.md)."),
    category: str = typer.Option("", "--category", "-c", help="Target category (default: strict)."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite target if it exists."),
    directory: str = typer.Option(".", "--dir", help="Repository directory (default: current)."),
):
    """Promote a document from draft to strict."""
    repo_dir = Path(directory)
    if not repo_dir.exists():
        typer.echo(f"Error: Directory '{directory}' not found.", err=True)
        sys.exit(1)
    has_args = bool(path or category)
    is_tty = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())
    interactive = not has_args and is_tty
    result = DocPromote(path=path, category=category, interactive=interactive).run(repo_dir)
    sys.exit(result or 0)


@doc_app.command("retire")
def doc_retire(
    path: str = typer.Option("", "--path", "-p", help="Document path to retire (e.g. docs/strict/1001.md)."),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for retirement."),
    directory: str = typer.Option(".", "--dir", help="Repository directory (default: current)."),
):
    """Retire a document."""
    repo_dir = Path(directory)
    if not repo_dir.exists():
        typer.echo(f"Error: Directory '{directory}' not found.", err=True)
        sys.exit(1)
    has_args = bool(path or reason)
    is_tty = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())
    interactive = not has_args and is_tty
    result = DocRetire(path=path, reason=reason, interactive=interactive).run(repo_dir)
    sys.exit(result or 0)


@app.command()
def doc(
    directory: str = typer.Option(".", "--dir", "-d", help="Repository directory (default: current)."),
    invisible: bool = typer.Option(False, "--info", help="Show document summary info."),
):
    """Manage documents locally.

    Use subcommands to create, promote (drafts->strict), or retire documents.
    Operations are applied to the working tree. Push and open a PR to have
    the CI verify and commit the changes.
    """
    repo_dir = Path(directory)
    if not repo_dir.exists():
        typer.echo(f"Error: Directory '{directory}' not found.", err=True)
        sys.exit(1)

    if invisible:
        # Show document summary
        from versioned_md.doc import _find_all_md, _parse_frontmatter

        categories = ("strict", "draft", "reference")
        doc_lists: dict[str, list[dict]] = {cat: [] for cat in categories}
        for cat in categories:
            cat_dir = repo_dir / "docs" / cat
            if not cat_dir.exists():
                continue
            for md_file in _find_all_md(cat_dir):
                try:
                    meta, _ = _parse_frontmatter(md_file)
                    doc_lists[cat].append(meta)
                except Exception:
                    continue

        for cat in categories:
            docs = doc_lists[cat]
            if cat_dir := repo_dir / "docs" / cat:
                if docs:
                    typer.echo(f"\n  {cat.upper()} ({len(docs)} documents)")
                    for meta in docs:
                        title = meta.get("title", "?")
                        did = meta.get("documentId", "")
                        version = meta.get("version", "?")
                        status = meta.get("status", "active")
                        status_str = " [retired]" if status == "retired" else ""
                        typer.echo(f"    {title:<40} @{did or '---':<7} v{version}{status_str}")

        return

    typer.echo("Use 'versioned-md doc <subcommand>' instead. Subcommands: create, promote, retire.")


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
    person_name: str = typer.Option(None, "--person-name", "-n", help="Initial person name."),
    person_handle: str = typer.Option(
        None, "--person-handle", "-h", help="Initial person handle (e.g. github username)."
    ),
    person_initials: str = typer.Option(None, "--person-initials", "-i", help="Initial person initials (e.g. JD)."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing template branches."),
):
    """Initialise template branches (main, TEMPLATE) and create people.json.

    Provide --person-name, --person-handle, --person-initials for non-interactive use,
    or run interactively in a terminal.
    """
    has_args = bool(person_name or person_handle or person_initials)
    import os
    import sys

    is_tty = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())
    run_interactive = not has_args and is_tty

    init_app = InitApplication(
        Path(directory),
        person_name=person_name or "",
        person_handle=person_handle or "",
        person_initials=person_initials or "",
        force=force,
        run_interactive=run_interactive,
    )
    result = init_app.run()
    sys.exit(result or 0)


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


@people_app.command("add")
def people_add(
    directory: str = typer.Option(".", "--dir", "-d", help="Repository directory (default: current)."),
    name: str = typer.Option(None, "--name", "-n", help="Person name."),
    handle: str = typer.Option(None, "--handle", "-h", help="Person handle (e.g. github username)."),
    initials: str = typer.Option(None, "--initials", "-i", help="Person initials (e.g. JD)."),
):
    """Add a person to the repository's people.json."""
    repo_dir = Path(directory)
    people_path = validate_people_path(repo_dir)
    has_args = bool(name or handle or initials)
    is_tty = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())
    interactive = not has_args and is_tty
    if interactive:
        name = typer.prompt("Name")
        handle = typer.prompt("Handle (e.g. github username)")
        initials = typer.prompt("Initials (e.g. JD)")
    result = add_person(people_path, name or "", handle or "", initials or "")
    sys.exit(result or 0)


@people_app.command("deactivate")
def people_deactivate(
    directory: str = typer.Option(".", "--dir", "-d", help="Repository directory (default: current)."),
    handle: str = typer.Option(None, "--handle", "-h", help="Person handle (e.g. github username)."),
):
    """Deactivate a person in the repository's people.json."""
    repo_dir = Path(directory)
    people_path = validate_people_path(repo_dir)
    if not handle:
        handle = typer.prompt("Person handle")
    result = deactivate_person(people_path, handle)
    sys.exit(result or 0)


if __name__ == "__main__":
    app()
