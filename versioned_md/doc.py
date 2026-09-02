"""Manage documents locally within a documentation repository."""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

VALID_CATEGORIES = ("strict", "draft")
CAT_DIR_MAP = {
    "strict": "docs/strict",
    "draft": "docs/drafts",
}
DOC_BODY_TEMPLATE = """# {title}

{description}

<!-- Add document content below -->

"""


def _ensure_people_json(repo_dir: Path) -> None:
    """Verify people.json exists in the repo."""
    if not (repo_dir / "people.json").exists():
        log.error("people.json not found. Run 'versioned-md init .' first.")
        sys.exit(1)


def _git_info() -> tuple[str, str]:
    """Return (author, date) from git."""
    import subprocess

    author = subprocess.run(
        ["git", "log", "--format=%an", "-1"], capture_output=True, text=True, check=False
    ).stdout.strip()
    date = subprocess.run(
        ["git", "log", "--format=%ad", "--date=short", "-1"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return author, date


def _get_file_history(repo_dir: Path, filepath: Path) -> tuple[str, str] | None:
    """Return (author, date) from the last commit affecting this file, tracing renames.

    Tries with the current path first, then without the repo_dir prefix.
    Returns None if no git history exists for the file.
    """
    import subprocess

    # Try relative path first, then bare filename
    for rel_path in (str(filepath), filepath.name):
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "log", "--follow", "--format=%an|||%ad", "--date=short", "-1", "--", rel_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|||", 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    # Last resort: plain git log on the filename only
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--format=%an|||%ad", "--date=short", "-50", "--", filepath.name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        lines = [line for line in result.stdout.strip().split("\n") if line]
        if lines:
            parts = lines[0].split("|||", 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    return None


def _load_counter(repo_dir: Path) -> int:
    """Load next document ID counter."""
    counter_path = repo_dir / ".doc_id_counter.json"
    if counter_path.exists():
        try:
            data = json.loads(counter_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return int(data.get("next_id", 1001))
        except Exception:
            pass
    return 1001


def _save_counter(repo_dir: Path, n: int) -> None:
    """Save next document ID counter."""
    counter_path = repo_dir / ".doc_id_counter.json"
    counter_path.write_text(json.dumps({"next_id": n}, indent=2) + "\n", encoding="utf-8")


def _next_id(repo_dir: Path, skip_ids: set[str] | None = None, *, save: bool = True) -> str:
    """Get and increment the next document ID, avoiding collisions."""
    skip_ids = skip_ids or set()
    candidate = _load_counter(repo_dir)
    while f"{candidate:04d}" in skip_ids:
        candidate += 1
    if save:
        _save_counter(repo_dir, candidate + 1)
    while f"{candidate:04d}" in skip_ids:
        candidate += 1
    return f"{candidate:04d}"


def _load_meta(path: Path) -> dict:
    """Load companion .meta.json for a document."""
    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {"version_history": []}


def _merge_version_history(
    dest_path: Path,
    source_history: list[dict],
    *,
    skip_existing: bool = False,
) -> list[dict]:
    """Merge source version_history into the destination's history.

    Skips entries that already exist in the destination (by version key).
    Sets action='imported' on copied entries.
    """
    dest_data = _load_meta(dest_path)
    dest_history = dest_data.get("version_history") or []
    dest_by_version = {h.get("version") for h in dest_history if h.get("version")}

    merged = list(dest_history)

    for entry in source_history:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if version and skip_existing and version in dest_by_version:
            continue
        if version:
            dest_by_version.add(version)
        entry_with_action = dict(entry)
        entry_with_action["action"] = entry_with_action.get("action") or "imported"
        merged.append(entry_with_action)

    return merged


def _merge_history_from_json(dest_path: Path, source_data: dict, *, skip_existing: bool = False) -> int:
    """Merge version_history from a JSON-parsed source .meta.json.

    Returns the number of entries that were actually imported.
    """
    source_history = source_data.get("version_history") or []
    merged = _merge_version_history(dest_path, source_history, skip_existing=skip_existing)
    return len([e for e in merged if e.get("action") == "imported"])


def _save_meta(path: Path, data: dict) -> None:
    """Save companion .meta.json for a document."""
    meta_path = path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _slugify(text: str) -> str:
    """Convert a string to a URL-safe slug."""
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def _find_all_md(base_dir: Path) -> list[Path]:
    """Find all .md files recursively in base_dir."""
    results = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".md"):
                results.append(Path(root) / f)
    return results


def _collect_existing_ids(repo_dir: Path, category: str) -> dict[str, Path]:
    """Map documentId to path for a given category, using .meta.json."""
    ids: dict[str, Path] = {}
    base = CAT_DIR_MAP.get(category)
    if not base:
        return ids
    base_path = repo_dir / base
    if not base_path.exists():
        return ids
    for md_file in _find_all_md(base_path):
        try:
            meta = _load_meta(md_file)
            did = meta.get("documentId", "")
            if did:
                ids[did] = md_file
        except Exception:
            continue
    return ids


def _validate_document_id(doc_id: str) -> None:
    """Validate that a documentId is a 4-digit number."""
    doc_id = str(doc_id)
    if not doc_id.isdigit():
        raise ValueError(f"DocumentId must be numeric: {doc_id}")
    if len(doc_id) != 4:
        raise ValueError(f"DocumentId must be 4 digits, got {len(doc_id)}: {doc_id}")


def _write_md_file(path: Path, title: str, description: str, body: str = "") -> None:
    """Write a plain markdown file (no frontmatter)."""
    if body:
        content = body
    else:
        content = DOC_BODY_TEMPLATE.format(title=title, description=description)
    path.write_text(content, encoding="utf-8")


class DocCreate:
    """Create a new document."""

    def __init__(
        self,
        title: str = "",
        category: str = "",
        description: str = "",
        interactive: bool = False,
    ):
        self.title = title
        self.category = category
        self.description = description
        self.interactive = interactive

    def run(self, repo_dir: Path) -> int:
        if not self.title:
            self.title = self._prompt("Document title")

        if not self.category:
            print("\nWhat kind of document is this?")
            print("  1) draft — work in progress, no governance")
            print("  2) strict — published documentation, requires documentId")
            while not self.category:
                choice = input("> ").strip()
                if choice == "1":
                    self.category = "draft"
                elif choice == "2":
                    self.category = "strict"
                else:
                    print("Please enter 1 or 2")

        if self.category not in ("strict", "draft"):
            log.error(f"Invalid category '{self.category}'. Must be 'draft' or 'strict'.")
            return 1

        if not self.description:
            self.description = self._prompt("Description", default="A new documentation document")

        # Build filename based on category
        doc_dir = Path(CAT_DIR_MAP.get(self.category, f"docs/{self.category}"))
        if self.category == "draft":
            # Drafts: use a slugified version of the title
            filename = self._make_slug(self.title) + ".md"
        else:
            # Strict: ask for the document number
            doc_number = self._prompt("Document number (e.g. 1001)")
            if not doc_number.isdigit():
                log.error("Document number must be numeric.")
                return 1
            if len(doc_number) != 4:
                log.error("Document number must be 4 digits.")
                return 1
            filename = doc_number + ".md"

        target_path = doc_dir / filename

        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Set documentId: use user-entered number for strict, auto-assign for draft
        if self.category == "strict":
            document_id = doc_number
        else:
            skip_ids = set()
            for cat in CAT_DIR_MAP:
                skip_ids.update(_collect_existing_ids(repo_dir, cat))
            document_id = _next_id(repo_dir, skip_ids)
            print(f"  Auto-assigned documentId: {document_id}")

        # Collect git info
        author, date = _git_info()
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Build .meta.json
        meta_json = {
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "documentId": document_id,
            "status": "active",
            "version": "0",
            "lastUpdated": today,
            "updatedBy": author,
            "reviewer": [],
            "commitHash": "",
            "prNumber": "",
            "version_history": [],
        }

        # Handle existing file vs new file
        if target_path.exists():
            log.info(f"Overwriting existing file: {target_path}")
        else:
            log.info(f"Creating: {target_path}")

        # Write plain markdown file (no frontmatter)
        _write_md_file(target_path, self.title, self.description)

        # Save .meta.json
        _save_meta(target_path, meta_json)

        log.info(f"Created document: {target_path}")
        log.info(f"  title: {self.title}")
        log.info(f"  category: {self.category}")
        log.info(f"  documentId: {document_id}")
        return 0

    def _prompt(self, message: str, default: str = "") -> str:
        if default:
            prompt_str = f"{message} [{default}]: "
        else:
            prompt_str = f"{message}: "
        value = input(prompt_str).strip()
        return value or default

    def _make_slug(self, text: str) -> str:
        """Convert a title to a slug for use in filenames."""
        return _slugify(text)


class DocPromote:
    """Promote a document from draft to strict."""

    def __init__(self, path: str = "", category: str = "", interactive: bool = False):
        self.path = path
        self.category = category
        self.interactive = interactive

    def run(self, repo_dir: Path) -> int:
        if not self.path:
            self.path = self._prompt("Document path (e.g. docs/drafts/my-doc.md)")

        if not self.category:
            self.category = self._prompt("Category", default="strict")

        src_path = Path(self.path)
        if not src_path.is_absolute():
            src_path = repo_dir / src_path

        if not src_path.exists():
            log.error(f"File not found: {src_path}")
            return 1

        meta = _load_meta(src_path)

        # Validate current category
        current_category = meta.get("category", "")
        if current_category not in ("draft",):
            log.error(
                f"Cannot promote '{src_path}'. Current category is '{current_category}' — only 'draft' can be promoted."
            )
            return 1

        if meta.get("category") == self.category:
            log.error("Document is already in the target category.")
            return 1

        # Determine destination path
        target_dir = repo_dir / CAT_DIR_MAP.get(self.category, f"docs/{self.category}")
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / src_path.name

        # For strict: rename to documentId
        document_id = meta.get("documentId", "")
        if self.category == "strict":
            if not document_id:
                skip_ids = set()
                for cat in CAT_DIR_MAP:
                    skip_ids.update(_collect_existing_ids(repo_dir, cat))
                if src_path.name.replace(".md", "") in skip_ids:
                    skip_ids.discard(src_path.name.replace(".md", ""))
                document_id = _next_id(repo_dir, skip_ids)
                log.info(f"Auto-assigned documentId for promotion: {document_id}")
            target_path = target_dir / f"{document_id}.md"

        # Validate uniqueness
        existing = _collect_existing_ids(repo_dir, self.category)
        if document_id in existing and existing[document_id] != src_path:
            log.error(f"DocumentId '{document_id}' already exists at {existing[document_id]}.")
            return 1

        # Update .meta.json fields
        meta["category"] = self.category
        meta["lastUpdated"] = datetime.now(UTC).strftime("%Y-%m-%d")
        meta["updatedBy"], _ = _git_info()

        # Handle .meta.json — move from old location
        old_meta_path = src_path.with_suffix(".meta.json")
        new_meta_path = target_path.with_suffix(".meta.json")
        if source_in_same_dir := src_path.parent == target_path.parent:
            old_meta_path = target_path.with_suffix(".meta.json")
            new_meta_path = old_meta_path
        if old_meta_path.exists() and not source_in_same_dir:
            import shutil

            shutil.copy2(old_meta_path, new_meta_path)
            # Will be updated further below
        elif old_meta_path.exists():
            import shutil

            shutil.copy2(old_meta_path, new_meta_path)
            new_meta_path = old_meta_path

        # Rename in-progress doc to avoid conflict
        if target_path.exists():
            log.error(f"Target path already exists: {target_path}. Remove or rename '{target_path}' before promoting.")
            return 1

        # Move the .md file
        import shutil

        shutil.copy2(src_path, target_path)
        src_path.unlink()
        log.info(f"Promoted: {src_path} -> {target_path}")

        # Update .meta.json at new location
        _save_meta(target_path, meta)

        log.info(f"  documentId: {meta.get('documentId')}")
        return 0

    def _prompt(self, message: str, default: str = "") -> str:
        if default:
            prompt_str = f"{message} [{default}]: "
        else:
            prompt_str = f"{message}: "
        value = input(prompt_str).strip()
        return value or default


class DocRetire:
    """Retire a document."""

    def __init__(self, path: str = "", reason: str = "", interactive: bool = False):
        self.path = path
        self.reason = reason
        self.interactive = interactive

    def run(self, repo_dir: Path) -> int:
        if not self.path:
            self.path = self._prompt("Document path (e.g. docs/strict/1001.md)")

        src_path = Path(self.path)
        if not src_path.is_absolute():
            src_path = repo_dir / src_path

        if not src_path.exists():
            log.error(f"File not found: {src_path}")
            return 1

        if not self.reason:
            self.reason = self._prompt("Reason for retirement", default="")

        meta = _load_meta(src_path)

        # Ensure retired directory exists
        retired_dir = repo_dir / "docs" / "retired"
        retired_dir.mkdir(parents=True, exist_ok=True)

        # Move file to retired directory
        retired_name = f"retired-{src_path.name}"
        new_path = retired_dir / retired_name

        if new_path.exists():
            log.error(f"File already exists at {new_path}")
            return 1

        import shutil

        shutil.copy2(src_path, new_path)
        src_path.unlink()
        log.info(f"Retired: {src_path} -> {new_path}")

        # Update .meta.json
        author, _ = _git_info()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        meta["status"] = "retired"
        meta["statusChangedBy"] = author
        meta["lastUpdated"] = today
        meta["updatedBy"] = author

        if self.reason:
            meta["retiredReason"] = self.reason

        # Save .meta.json at new location
        _save_meta(new_path, meta)

        log.info("  status: retired")
        log.info(f"  reason: {self.reason or '(none provided)'}")
        return 0

    def _prompt(self, message: str, default: str = "") -> str:
        if default:
            prompt_str = f"{message} [{default}]: "
        else:
            prompt_str = f"{message}: "
        value = input(prompt_str).strip()
        return value or default


class DocImport:
    """Import an existing markdown file into the versioned-md structure."""

    def __init__(
        self,
        source: str = "",
        category: str = "",
        document_id: str = "",
        interactive: bool = False,
        dry_run: bool = False,
        force: bool = False,
        skip_existing: bool = False,
        skip_history: bool = False,
    ):
        self.source = source
        self.category = category
        self.document_id = document_id
        self.interactive = interactive
        self.dry_run = dry_run
        self.force = force
        self.skip_existing = skip_existing
        self.skip_history = skip_history

    def run(self, repo_dir: Path) -> int:
        source_path = Path(self.source)
        if not source_path.is_absolute():
            source_path = repo_dir / source_path

        if not source_path.exists():
            log.error(f"Source file not found: {source_path}")
            return 1

        if not self.source.endswith(".md"):
            log.error(f"Source file must be a markdown file (.md): {source_path}")
            return 1

        # Read the source markdown body (no frontmatter)
        body = source_path.read_text(encoding="utf-8") if source_path.exists() else ""

        if not body.strip():
            log.error(f"Source file has no body content: {source_path}")
            return 1

        # Determine category
        if not self.category:
            if self.interactive:
                self.category = self._prompt("Category (strict or draft)", default="draft")
            else:
                log.error("No category provided. Use --category or add 'category:' to source .meta.json.")
                return 1

        if self.category not in VALID_CATEGORIES:
            log.error(f"Invalid category '{self.category}'. Must be 'strict' or 'draft'.")
            return 1

        # Handle documentId
        document_id = self.document_id or ""

        if self.category == "strict":
            # Strict documents require a 4-digit documentId
            if not document_id and self.interactive:
                document_id = self._prompt("Document number (e.g. 1001)")
            elif not document_id:
                log.error("Strict documents require a documentId. Provide --document-id.")
                return 1
            _validate_document_id(document_id)
            document_id = str(document_id)
        else:
            # Draft: auto-assign if missing
            if not document_id:
                skip_ids = set()
                for cat in VALID_CATEGORIES:
                    skip_ids.update(_collect_existing_ids(repo_dir, cat))
                document_id = _next_id(repo_dir, skip_ids, save=not self.dry_run)
                log.info(f"Auto-assigned documentId: {document_id}")

        # Enrich with git history for source file
        git_history = _get_file_history(repo_dir, source_path)
        author = git_history[0] if git_history else None
        date = git_history[1] if git_history else None
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # Determine target path
        target_dir = repo_dir / CAT_DIR_MAP.get(self.category, f"docs/{self.category}")
        if self.category == "draft":
            title = source_path.stem.replace("-", " ").title()
            slug = _slugify(title)
            filename = slug + ".md"
        else:
            filename = f"{document_id}.md"

        target_path = target_dir / filename

        if target_path.exists():
            if self.skip_existing:
                log.info(f"Skipping existing document: {target_path}")
                return 0
            if not self.force:
                log.error(f"Target already exists: {target_path}. Use --force to overwrite or --dry-run to preview.")
                return 1
            log.warning(f"Overwriting existing target: {target_path}")

        # Dry-run: just report
        if self.dry_run:
            log.info(f"[DRY RUN] Would create: {target_path}")
            log.info(f"  category: {self.category}")
            log.info(f"  documentId: {document_id}")
            if source_path.exists():
                log.info(f"  source: {source_path}")
            source_meta_path = source_path.with_suffix(".meta.json")
            if not self.skip_history and source_meta_path.exists():
                try:
                    source_meta_data = json.loads(source_meta_path.read_text(encoding="utf-8")) or {}
                except (json.JSONDecodeError, FileNotFoundError):
                    source_meta_data = {}
                history = source_meta_data.get("version_history") or []
                merged = _merge_version_history(target_path, history, skip_existing=self.skip_existing)
                log.info(f"  version_history: {len(history)} entries")
                skipped = len(history) - len([e for e in merged if e.get("action") == "imported"])
                if skipped:
                    log.info(f"  {skipped} versions already exist (skipped with --skip-existing)")
            elif self.skip_history:
                log.info("  version_history: skipped (--skip-history)")
            else:
                log.info("  version_history: no source .meta.json found")
            return 0

        # Create target directory and write plain markdown
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Title for the markdown body
        title = source_path.stem.replace("-", " ").title()

        # Build .meta.json with all top-level fields
        meta_json = {
            "title": title,
            "description": "",
            "category": self.category,
            "documentId": document_id,
            "status": "active",
            "version": "0",
            "lastUpdated": date or today,
            "updatedBy": author or _git_info()[0],
            "reviewer": [],
            "commitHash": "",
            "prNumber": "",
            "version_history": [],
        }

        # Merge version_history from source .meta.json
        source_meta_path = source_path.with_suffix(".meta.json")
        if not self.skip_history and source_meta_path.exists():
            try:
                source_meta_data = json.loads(source_meta_path.read_text(encoding="utf-8")) or {}
                history = source_meta_data.get("version_history") or []

                # Preserve title/description from source if available
                if source_meta_data.get("title"):
                    meta_json["title"] = source_meta_data["title"]
                if source_meta_data.get("description"):
                    meta_json["description"] = source_meta_data["description"]

                meta_json["version_history"] = _merge_version_history(
                    target_path, history, skip_existing=self.skip_existing
                )
                imported = len([e for e in meta_json["version_history"] if e.get("action") == "imported"])
                log.info(f"  version_history: {imported} entries imported")
            except (json.JSONDecodeError, FileNotFoundError):
                meta_json["version_history"] = []
                log.info("  version_history: no valid source .meta.json found")
        else:
            meta_json["version_history"] = []
            if self.skip_history:
                log.info("  version_history: skipped (--skip-history)")
            else:
                log.info("  version_history: no source .meta.json found")

        # Write plain markdown file (no frontmatter)
        _write_md_file(target_path, meta_json["title"], meta_json.get("description", ""), body)

        # Save .meta.json
        _save_meta(target_path, meta_json)

        log.info(f"Imported: {source_path} -> {target_path}")
        log.info(f"  title: {meta_json.get('title')}")
        log.info(f"  category: {self.category}")
        log.info(f"  documentId: {document_id}")

        return 0

    def _prompt(self, message: str, default: str = "") -> str:
        if default:
            prompt_str = f"{message} [{default}]: "
        else:
            prompt_str = f"{message}: "
        value = input(prompt_str).strip()
        return value or default
