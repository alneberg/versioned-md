"""Manage documents locally within a documentation repository."""

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

VALID_CATEGORIES = ("strict", "draft", "reference")
CAT_DIR_MAP = {
    "strict": "docs/strict",
    "draft": "docs/drafts",
    "reference": "docs/reference",
}
CAT_PROMPTS = {
    "strict": "Category 'strict' (docs/strict/) — full governance, unique ID required",
    "draft": "Category 'draft' (docs/drafts/) — in-progress work",
    "reference": "Category 'reference' (docs/reference/) — independent reference docs",
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


def _next_id(repo_dir: Path) -> str:
    """Get and increment the next document ID."""
    counter = _load_counter(repo_dir)
    _save_counter(repo_dir, counter + 1)
    return f"{counter:04d}"


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
        path: str | Path = "",
        title: str = "",
        category: str = "",
        description: str = "",
        interactive: bool = False,
    ):
        self.path = str(path)
        self.title = title
        self.category = category
        self.description = description
        self.interactive = interactive

    def run(self, repo_dir: Path) -> int:
        if not self.path:
            self.path = self._prompt("Document path (e.g. docs/drafts/my-doc.md)")

        if not self.title:
            self.title = self._prompt("Document title")

        if not self.category:
            print("\nSelect category:")
            for cat in VALID_CATEGORIES:
                print(f"  {cat} — {CAT_PROMPTS[cat]}")
            while not self.category:
                self.category = input("> ").strip().lower()

        if self.category not in VALID_CATEGORIES:
            log.error(f"Invalid category '{self.category}'. Must be one of: {', '.join(VALID_CATEGORIES)}")
            return 1

        if not self.description:
            self.description = self._prompt("Description", default="A new documentation document")

        if not self.interactive:
            if not self.title or not self.path or not self.category:
                log.error("Not running interactively. Provide --title, --path, and --category.")
                return 1

        # Determine target path
        target_path = Path(self.path)
        if not target_path.is_absolute():
            target_path = repo_dir / target_path

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

        # Auto-assign documentId for strict and draft
        if self.category in ("strict", "draft") and not meta.get("documentId"):
            meta["documentId"] = _next_id(repo_dir)
            print(f"  Auto-assigned documentId: {meta['documentId']}")

        # Ensure strict filename matches documentId
        if self.category == "strict" and meta.get("documentId"):
            expected_name = meta["documentId"]
            if target_path.stem != expected_name:
                new_path = target_path.with_name(f"{expected_name}.md")
                if not new_path.exists():
                    log.info(f"Renaming to match documentId: {target_path.name} -> {expected_name}.md")
                    target_path = new_path
                elif target_path.stem != expected_name:
                    log.error(
                        f"Strict filename must match documentId exactly. "
                        f"'{target_path.name}' doesn't match documentId '{meta['documentId']}'. "
                        f"Rename '{target_path.name}' to '{expected_name}.md'."
                    )
                    return 1

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
                # Auto-assign a documentId
                document_id = _next_id(repo_dir)
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
