# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog fragment support."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE

FRAGMENT_DIR_CANDIDATES = ("changelog.d", "changes", ".changelogmanager/fragments")
FILENAME_RE = re.compile(r"^(?P<slug>.+)\.(?P<change_type>[a-z]+)\.md$")


@dataclass(frozen=True)
class ChangelogFragment:
    path: Path
    slug: str
    change_type: str
    text: str


def discover_fragment_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in FRAGMENT_DIR_CANDIDATES:
        path = Path(candidate)
        if path.is_dir():
            return path
    return Path(FRAGMENT_DIR_CANDIDATES[0])


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80].strip("-") or "change"


def fragment_path(fragment_dir: Path, change_type: str, text: str, slug: str | None) -> Path:
    if change_type not in TYPES_OF_CHANGE:
        raise logging.Error(message=f"Unknown change type '{change_type}'")
    final_slug = slugify(slug or text)
    return fragment_dir / f"{final_slug}.{change_type}.md"


def write_fragment(
    fragment_dir: Path,
    change_type: str,
    text: str,
    slug: str | None = None,
    *,
    force: bool = False,
) -> Path:
    cleaned = text.strip()
    if not cleaned:
        raise logging.Error(message="Fragment text must not be empty")

    path = fragment_path(fragment_dir, change_type, cleaned, slug)
    same_slug = list(fragment_dir.glob(f"{path.name.rsplit('.', 2)[0]}.*.md"))
    conflicts = [candidate for candidate in same_slug if candidate != path]
    if conflicts and not force:
        raise logging.Error(
            file_path=str(conflicts[0]),
            message="Fragment slug already exists with a different change type",
        )

    fragment_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(cleaned.rstrip() + "\n", encoding="UTF-8")
    return path


def parse_fragment_path(path: Path) -> tuple[str, str] | None:
    match = FILENAME_RE.match(path.name)
    if not match:
        return None
    change_type = match.group("change_type")
    if change_type not in CATEGORIES:
        return None
    return match.group("slug"), change_type


def read_fragments(fragment_dir: Path) -> list[ChangelogFragment]:
    if not fragment_dir.is_dir():
        return []
    fragments: list[ChangelogFragment] = []
    for path in sorted(fragment_dir.glob("*.md")):
        parsed = parse_fragment_path(path)
        if parsed is None:
            continue
        text = path.read_text(encoding="UTF-8").strip()
        if not text:
            continue
        slug, change_type = parsed
        fragments.append(
            ChangelogFragment(
                path=path,
                slug=slug,
                change_type=change_type,
                text=text,
            )
        )
    return fragments


def validate_fragments(fragment_dir: Path) -> list[str]:
    errors: list[str] = []
    if not fragment_dir.exists():
        return errors
    seen: set[tuple[str, str]] = set()
    for path in sorted(fragment_dir.glob("*.md")):
        parsed = parse_fragment_path(path)
        if parsed is None:
            errors.append(f"{path}: filename must be <slug>.<type>.md")
            continue
        slug, change_type = parsed
        text = path.read_text(encoding="UTF-8").strip()
        if not text:
            errors.append(f"{path}: fragment text must not be empty")
        key = (change_type, text)
        if key in seen:
            errors.append(f"{path}: duplicate fragment text")
        seen.add(key)
        if not slug:
            errors.append(f"{path}: fragment slug must not be empty")
    return errors


def consume_fragments(
    fragments: list[ChangelogFragment], mode: str, archive_directory: Path | None = None
) -> list[Path]:
    consumed: list[Path] = []
    if mode == "keep":
        return consumed
    if mode not in {"archive", "delete"}:
        raise logging.Error(message="--consume must be archive, delete, or keep")
    for fragment in fragments:
        if mode == "delete":
            fragment.path.unlink()
            consumed.append(fragment.path)
            continue
        archive_root = archive_directory or fragment.path.parent / "archive"
        target_dir = archive_root / date.today().isoformat()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / fragment.path.name
        shutil.move(str(fragment.path), str(target))
        consumed.append(target)
    return consumed

