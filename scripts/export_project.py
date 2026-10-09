#!/usr/bin/env python3
"""Export this Python project as a clean source ZIP for AI review.

Run from anywhere: python scripts/export_project.py
Requires only Python 3.11+ (no project dependencies).
"""

from __future__ import annotations

import os
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "exports"

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".venv", "venv", "virtualenv", ".virtualenv",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".ty_cache",
    ".tox", ".nox", ".hypothesis", ".cache", ".uv", "site-packages",
    "node_modules", ".pnpm-store", ".yarn", ".next", ".nuxt", ".output",
    ".turbo", ".vite", ".parcel-cache", ".svelte-kit", ".angular",
    "dist", "build", "out", "coverage", "htmlcov", "test-results", "playwright-report",
    "storybook-static", "exports",
}
SKIP_FILES = {
    ".ds_store", "thumbs.db", "desktop.ini", ".envrc", ".npmrc", ".pypirc", ".netrc",
    "credentials.json", "secrets.json", "service-account.json", "service_account.json",
    "id_rsa", "id_ed25519", "id_ecdsa", ".coverage",
}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".log", ".whl", ".egg", ".exe", ".dll", ".so", ".dylib",
    ".class", ".o", ".obj", ".map", ".pem", ".key", ".p12", ".pfx", ".jks",
    ".keystore", ".sqlite", ".sqlite3", ".db",
}
ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
LARGE_FILE_BYTES = 20 * 1024 * 1024


def is_environment_secret(name: str) -> bool:
    lower = name.lower()
    if lower in ENV_EXAMPLES or (lower.startswith(".env.") and lower.endswith((".example", ".sample", ".template"))):
        return False
    return lower == ".env" or lower.startswith(".env.") or lower.endswith(".env")


def skip_file(path: Path) -> bool:
    lower = path.name.lower()
    return (
        path.is_symlink()
        or lower in SKIP_FILES
        or is_environment_secret(lower)
        or path.suffix.lower() in SKIP_EXTENSIONS
        or lower.endswith(".egg-info")
    )


def project_name() -> str:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        try:
            with pyproject.open("rb") as handle:
                name = tomllib.load(handle).get("project", {}).get("name")
            if isinstance(name, str) and name.strip():
                return re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip(".-_")
        except (OSError, ValueError):
            pass
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", PROJECT_ROOT.name).strip(".-_") or "project"


def source_files() -> tuple[list[Path], int]:
    files: list[Path] = []
    skipped = 0
    for base, dirs, names in os.walk(PROJECT_ROOT, topdown=True, followlinks=False):
        base_path = Path(base)
        keep_dirs = []
        for directory in sorted(dirs):
            full_path = base_path / directory
            if directory.lower() in SKIP_DIRS or directory.lower().endswith(".egg-info") or full_path.is_symlink():
                skipped += 1
            else:
                keep_dirs.append(directory)
        dirs[:] = keep_dirs
        for name in sorted(names):
            path = base_path / name
            if not path.is_file() or skip_file(path):
                skipped += 1
            else:
                files.append(path)
    return files, skipped


def main() -> None:
    name = project_name()
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output = OUTPUT_DIR / f"{name}-ai-source-{timestamp}.zip"
    index = 2
    while output.exists():
        output = OUTPUT_DIR / f"{name}-ai-source-{timestamp}-{index}.zip"
        index += 1

    files, skipped = source_files()
    temp_output = output.with_suffix(".zip.tmp")
    total_bytes = 0
    large: list[str] = []

    try:
        with ZipFile(temp_output, "w", compression=ZIP_DEFLATED, compresslevel=6, strict_timestamps=False) as archive:
            for path in files:
                rel_path = path.relative_to(PROJECT_ROOT)
                size = path.stat().st_size
                total_bytes += size
                if size > LARGE_FILE_BYTES:
                    large.append(str(rel_path))
                archive.write(path, arcname=f"{name}/{rel_path.as_posix()}")
        temp_output.replace(output)
    finally:
        temp_output.unlink(missing_ok=True)

    print(f"Created: {output}")
    print(f"Included: {len(files)} files ({total_bytes / 1024 / 1024:.2f} MiB before compression)")
    print(f"Excluded: {skipped} generated, sensitive, or linked entries")
    print(f"ZIP size: {output.stat().st_size / 1024 / 1024:.2f} MiB")
    if large:
        print("Large files included (review before sharing):")
        for item in large:
            print(f"  {item}")
    print("Review the ZIP for any other project-specific secrets before uploading to an AI service.")


if __name__ == "__main__":
    main()
