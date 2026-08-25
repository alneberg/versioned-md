"""Manage documents locally within a documentation repository."""

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

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
            data = yaml.safe_load(counter_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return int(data.get("next_id", 1001))
        except Exception:
            pass
    return 1001


def _save_counter(repo_dir: Path, n: int) -> None:
    """Save next document ID counter."""
    counter_path = repo_dir / ".doc_id_counter.json"
    counter_path.write_text(yaml.dump({"next_id": n}, default_flow_style=False) + "\n", encoding="utf-8")


def _next_id(repo_dir: Path, skip_ids: set[str] | None = None) -> str:
    """Get and increment the next document ID, avoiding collisions."""
    skip_ids = skip_ids or set()
    candidate = _load_counter(repo_dir)
    while f"{candidate:04d}" in skip_ids:
        candidate += 1
    _save_counter(repo_dir, candidate + 1)
    while f"{candidate:04d}" in skip_ids:
        candidate += 1
    return f"{candidate:04d}"


def _load_meta(path: Path) -> dict:
    """Load companion .meta.json for a document."""
    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {"version_history": []}


def _save_meta(path: Path, data: dict) -> None:
    """Save companion .meta.json for a document."""
    meta_path = path.with_suffix(".meta.json")
    meta_path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True) + "\n", encoding="utf-8")


def _slugify(text: str) -> str:
    """Convert a string to a URL-safe slug."""
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def _parse_frontmatter(path: Path) -> tuple[dict, str]:
    """Parse frontmatter and body from a markdown file."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"No frontmatter found in {path}")
    fm_end = 1
    while fm_end < len(lines):
        if lines[fm_end].strip() == "---":
            break
        fm_end += 1
    else:
        raise ValueError(f"No closing --- in frontmatter of {path}")
    fm_text = "\n".join(lines[1:fm_end])
    body = "\n".join(lines[fm_end + 1 :]) if fm_end + 1 < len(lines) else ""
    meta = yaml.safe_load(fm_text) or {}
    return meta, body


def _write_frontmatter(path: Path, meta: dict, body: str) -> None:
    """Rewrite frontmatter while preserving body."""
    fm = "---\n" + yaml.dump(meta, default_flow_style=False, allow_unicode=True) + "---\n"
    path.write_text(fm + body, encoding="utf-8")


def _find_all_md(base_dir: Path) -> list[Path]:
    """Find all .md files recursively in base_dir."""
    results = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".md"):
                results.append(Path(root) / f)
    return results


def _collect_existing_ids(repo_dir: Path, category: str) -> dict[str, Path]:
    """Map documentId to path for a given category."""
    ids: dict[str, Path] = {}
    base = CAT_DIR_MAP.get(category)
    if not base:
        return ids
    base_path = repo_dir / base
    if not base_path.exists():
        return ids
    for md_file in _find_all_md(base_path):
        try:
            meta, _ = _parse_frontmatter(md_file)
            did = meta.get("documentId", "")
            if did:
                ids[did] = md_file
        except Exception:
            continue
    return ids


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

        # Auto-fill fields
        meta, existing_body = _parse_frontmatter(target_path) if target_path.exists() else ({}, "")

        if not meta.get("title"):
            meta["title"] = self.title
        if not meta.get("description"):
            meta["description"] = self.description
        if not meta.get("category"):
            meta["category"] = self.category

        # Set documentId: use user-entered number for strict, auto-assign for draft
        if self.category == "strict":
            meta["documentId"] = doc_number
        else:
            if not meta.get("documentId"):
                # Collect IDs from all categories to avoid collisions
                skip_ids = set()
                for cat in CAT_DIR_MAP:
                    skip_ids.update(_collect_existing_ids(repo_dir, cat))
                meta["documentId"] = _next_id(repo_dir, skip_ids)
                print(f"  Auto-assigned documentId: {meta['documentId']}")

        # Populate remaining metadata
        if not meta.get("lastUpdated"):
            meta["lastUpdated"] = datetime.now(UTC).strftime("%Y-%m-%d")
        if not meta.get("updatedBy"):
            meta["updatedBy"], _ = _git_info()
        if not meta.get("version"):
            meta["version"] = "0"
        if not meta.get("prNumber"):
            meta["prNumber"] = ""
        if not meta.get("commitHash"):
            meta["commitHash"] = ""

        # Build document body if none exists
        if not existing_body.strip():
            body = DOC_BODY_TEMPLATE.format(title=self.title, description=self.description)
        else:
            body = existing_body

        # Handle existing file
        if target_path.exists():
            # Merge frontmatter
            pass
        else:
            log.info(f"Creating: {target_path}")

        _write_frontmatter(target_path, meta, body)

        # Create .meta.json if it doesn't exist
        meta_path = target_path.with_suffix(".meta.json")
        if not meta_path.exists():
            _save_meta(target_path, {"version_history": []})

        log.info(f"Created document: {target_path}")
        log.info(f"  title: {meta.get('title')}")
        log.info(f"  category: {meta.get('category')}")
        log.info(f"  documentId: {meta.get('documentId', 'N/A')}")
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

        meta, body = _parse_frontmatter(src_path)

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
                # Auto-assign a documentId, skipping IDs used in other categories
                skip_ids = set()
                for cat in CAT_DIR_MAP:
                    skip_ids.update(_collect_existing_ids(repo_dir, cat))
                if src_path.name.replace(".md", "") in skip_ids:
                    skip_ids.discard(src_path.name.replace(".md", ""))
                document_id = _next_id(repo_dir, skip_ids)
                log.info(f"Auto-assigned documentId for promotion: {document_id}")
                meta["documentId"] = document_id
            target_path = target_dir / f"{document_id}.md"

        # Validate uniqueness
        existing = _collect_existing_ids(repo_dir, self.category)
        if document_id in existing and existing[document_id] != src_path:
            log.error(f"DocumentId '{document_id}' already exists at {existing[document_id]}.")
            return 1

        # Update frontmatter
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

        # Rename in-progress doc to avoid conflict
        if target_path.exists():
            log.error(f"Target path already exists: {target_path}. Remove or rename '{target_path}' before promoting.")
            return 1

        # Move the file
        import shutil

        shutil.copy2(src_path, target_path)
        src_path.unlink()
        log.info(f"Promoted: {src_path} -> {target_path}")

        # Update frontmatter
        _write_frontmatter(target_path, meta, body)

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

        meta, body = _parse_frontmatter(src_path)

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

        # Update frontmatter
        meta["status"] = "retired"
        meta["retiredBy"], _ = _git_info()
        meta["retiredDate"] = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.reason:
            meta["retiredReason"] = self.reason
        meta["lastUpdated"] = datetime.now(UTC).strftime("%Y-%m-%d")
        meta["updatedBy"], _ = _git_info()

        _write_frontmatter(new_path, meta, body)

        # Copy .meta.json companion file too
        src_meta = src_path.with_suffix(".meta.json")
        new_meta = new_path.with_suffix(".meta.json")
        if src_meta.exists():
            import shutil

            shutil.copy2(src_meta, new_meta)

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


def _validate_document_id(doc_id: str) -> None:
    """Validate that a documentId is a 4-digit number."""
    doc_id = str(doc_id)
    if not doc_id.isdigit():
        raise ValueError(f"DocumentId must be numeric: {doc_id}")
    if len(doc_id) != 4:
        raise ValueError(f"DocumentId must be 4 digits, got {len(doc_id)}: {doc_id}")


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
    ):
        self.source = source
        self.category = category
        self.document_id = document_id
        self.interactive = interactive
        self.dry_run = dry_run
        self.force = force
        self.skip_existing = skip_existing

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

        try:
            meta, body = _parse_frontmatter(source_path)
        except ValueError as exc:
            log.error(f"Cannot parse frontmatter from {source_path}: {exc}")
            return 1
        except Exception as exc:
            log.error(
                f"Frontmatter parsing error in {source_path}: {exc}\n"
                "Hint: ensure frontmatter values with colons are quoted, "
                "e.g. 'title: \"WIP: Feature Guide\"'"
            )
            return 1

        if not body.strip():
            log.error(f"Source file has no body content: {source_path}")
            return 1

        # Determine category
        if not self.category:
            frontmatter_cat = meta.get("category", "")
            if frontmatter_cat in VALID_CATEGORIES:
                self.category = frontmatter_cat
            elif self.interactive:
                self.category = self._prompt("Category (strict or draft)", default="draft")
            else:
                log.error("No category and none in frontmatter. Use --category or add 'category:' to frontmatter.")
                return 1

        if self.category not in VALID_CATEGORIES:
            log.error(f"Invalid category '{self.category}'. Must be 'strict' or 'draft'.")
            return 1

        # Handle documentId
        document_id = meta.get("documentId", "")

        if self.category == "strict":
            # Strict documents require a 4-digit documentId
            if self.document_id:
                document_id = self.document_id
            elif not document_id and self.interactive:
                document_id = self._prompt("Document number (e.g. 1001)")
            elif not document_id:
                log.error(
                    "Strict documents require a documentId. Provide --document-id, or set documentId in frontmatter."
                )
                return 1
            _validate_document_id(document_id)
            document_id = str(document_id)
            meta["documentId"] = document_id
        else:
            # Draft: auto-assign if missing
            if not document_id:
                skip_ids = set()
                for cat in VALID_CATEGORIES:
                    skip_ids.update(_collect_existing_ids(repo_dir, cat))
                meta["documentId"] = _next_id(repo_dir, skip_ids)
                document_id = meta["documentId"]
                log.info(f"Auto-assigned documentId: {document_id}")
            else:
                meta["documentId"] = document_id

        # Enrich with git history for source file
        git_history = _get_file_history(repo_dir, source_path)
        if git_history:
            meta["updatedBy"] = git_history[0]
            meta["lastUpdated"] = git_history[1]
        else:
            if not meta.get("updatedBy"):
                meta["updatedBy"], _ = _git_info()
            if not meta.get("lastUpdated"):
                meta["lastUpdated"] = datetime.now(UTC).strftime("%Y-%m-%d")

        # Populate remaining fields
        if not meta.get("version"):
            meta["version"] = "0"
        if not meta.get("title"):
            meta["title"] = source_path.stem.replace("-", " ").title()
        if not meta.get("category"):
            meta["category"] = self.category

        # Determine target path
        target_dir = repo_dir / CAT_DIR_MAP.get(self.category, f"docs/{self.category}")
        if self.category == "draft":
            title = meta.get("title", source_path.stem)
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
            log.info(f"  title: {meta.get('title')}")
            log.info(f"  category: {self.category}")
            log.info(f"  documentId: {document_id}")
            if source_path.exists():
                log.info(f"  source: {source_path}")
            return 0

        # Create target directory and write
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _write_frontmatter(target_path, meta, body)

        # Create companion .meta.json
        _save_meta(target_path, {"version_history": []})

        log.info(f"Imported: {source_path} -> {target_path}")
        log.info(f"  title: {meta.get('title')}")
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
