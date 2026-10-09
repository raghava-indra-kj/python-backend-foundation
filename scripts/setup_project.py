"""One-time, dependency-free initializer for repositories created from this template."""

from __future__ import annotations

import json
import keyword
import re
import shutil
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DISTRIBUTION = "python-backend-foundation"
TEMPLATE_PACKAGE = "python_backend_foundation"
TEMPLATE_DISPLAY_NAME = "Python Backend Foundation"

# Prevent confusing import collisions with dependencies used by the scaffold.
RESERVED_PACKAGES = {
    "anyio",
    "fastapi",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "ruff",
    "starlette",
    "ty",
    "typing_extensions",
    "uv",
    "uvicorn",
    "uv_build",
}


def normalize_name(value: str) -> tuple[str, str]:
    """Return a distribution name and import-package name for a display name."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    distribution = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    package = distribution.replace("-", "_")

    if not distribution or len(distribution) > 100:
        raise ValueError("The project name must produce a distribution name of 1–100 characters.")

    if not package.isidentifier() or keyword.iskeyword(package):
        raise ValueError("The project name does not produce a valid Python package identifier.")

    if package in sys.stdlib_module_names or package in RESERVED_PACKAGES:
        raise ValueError(f"The Python package name {package!r} conflicts with an existing module.")

    if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", package):
        raise ValueError("The project name is reserved by Windows.")

    return distribution, package


def require_exactly_one(source: str, expected: str, *, description: str) -> None:
    if source.count(expected) != 1:
        raise RuntimeError(f"Expected exactly one {description}; template layout has changed.")


def setup_project(display_name: str) -> None:
    """Rename template identifiers, initialize local env, and regenerate uv.lock."""
    distribution, package = normalize_name(display_name)
    project_path = ROOT / "pyproject.toml"
    env_example_path = ROOT / "env" / ".env.example"
    env_local_path = ROOT / "env" / ".env"
    lock_path = ROOT / "uv.lock"
    source_package = ROOT / "src" / TEMPLATE_PACKAGE
    target_package = ROOT / "src" / package

    project_text = project_path.read_text(encoding="utf-8")
    project = tomllib.loads(project_text)
    current_distribution = project["project"]["name"]

    if current_distribution != TEMPLATE_DISTRIBUTION:
        if current_distribution == distribution and target_package.is_dir():
            print("Project has already been initialized with this name; nothing changed.")
            return
        raise RuntimeError("This project was already initialized with a different name.")

    if distribution == TEMPLATE_DISTRIBUTION or package == TEMPLATE_PACKAGE:
        raise ValueError("Choose a name different from Python Backend Foundation.")

    if not source_package.is_dir():
        raise FileNotFoundError(f"Missing template source package: {source_package}")
    if target_package.exists():
        raise FileExistsError(f"Target Python package already exists: {target_package}")
    if shutil.which("uv") is None:
        raise RuntimeError("uv must be installed and available on PATH before project initialization.")

    source_files = sorted(source_package.rglob("*.py"))
    if not source_files:
        raise RuntimeError("The template source package does not contain any Python files.")

    original = {file: file.read_text(encoding="utf-8") for file in [project_path, env_example_path, *source_files]}
    transformed = original.copy()

    project_name_line = f'name = "{TEMPLATE_DISTRIBUTION}"'
    description_line = 'description = "A reusable, modular Python backend foundation."'
    entry_point_line = f'backend-dev = "{TEMPLATE_PACKAGE}.cli:main"'
    require_exactly_one(project_text, project_name_line, description="project name in pyproject.toml")
    require_exactly_one(project_text, description_line, description="project description in pyproject.toml")
    require_exactly_one(project_text, entry_point_line, description="backend-dev entry point")

    transformed[project_path] = (
        project_text.replace(project_name_line, f'name = "{distribution}"', 1)
        .replace(description_line, f'description = "Backend application: {distribution}"', 1)
        .replace(entry_point_line, f'backend-dev = "{package}.cli:main"', 1)
    )

    env_example = original[env_example_path]
    env_title_pattern = r"^APP_NAME=.*$"
    if len(re.findall(env_title_pattern, env_example, flags=re.MULTILINE)) != 1:
        raise RuntimeError("Expected exactly one APP_NAME entry in env/.env.example.")

    transformed[env_example_path] = re.sub(
        env_title_pattern,
        lambda _match: f"APP_NAME={json.dumps(display_name, ensure_ascii=False)}",
        env_example,
        count=1,
        flags=re.MULTILINE,
    )

    config_path = source_package / "config.py"
    default_name_line = f'name: str = "{TEMPLATE_DISPLAY_NAME}"'
    require_exactly_one(original[config_path], default_name_line, description="default application name in config.py")

    for file in source_files:
        updated_source = original[file].replace(TEMPLATE_PACKAGE, package)
        if file == config_path:
            updated_source = updated_source.replace(default_name_line, f"name: str = {display_name!r}", 1)
        transformed[file] = updated_source

    original_lock = lock_path.read_bytes() if lock_path.exists() else None
    package_moved = False
    env_created = False

    def actual_path(original_path: Path) -> Path:
        if package_moved and original_path.is_relative_to(source_package):
            return target_package / original_path.relative_to(source_package)
        return original_path

    try:
        source_package.rename(target_package)
        package_moved = True

        for file, updated_content in transformed.items():
            if original[file] != updated_content:
                actual_path(file).write_text(updated_content, encoding="utf-8")

        try:
            with env_local_path.open("x", encoding="utf-8") as local_env:
                env_created = True
                local_env.write(transformed[env_example_path])
            print("Created env/.env from env/.env.example.")
        except FileExistsError:
            print("Existing env/.env preserved without changes.")

        # This generates/updates the lockfile for the new distribution name.
        subprocess.run(["uv", "lock"], cwd=ROOT, check=True)

    except BaseException:
        for file, original_content in original.items():
            path = actual_path(file)
            if path.exists():
                path.write_text(original_content, encoding="utf-8")

        if package_moved:
            target_package.rename(source_package)

        if env_created:
            env_local_path.unlink(missing_ok=True)

        if original_lock is None:
            lock_path.unlink(missing_ok=True)
        else:
            lock_path.write_bytes(original_lock)
        raise

    print(f"\nProject initialized: {display_name}")
    print(f"Distribution: {distribution}")
    print(f"Import package: {package}")
    print("\nNext: uv sync --locked")
    print("Then: uv run backend-dev")


def main() -> None:
    print("\nPython Backend Foundation — Project Setup\n")
    display_name = " ".join(input("What is your project name? ").split())
    if not display_name:
        raise ValueError("The project name cannot be empty.")
    setup_project(display_name)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nSetup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
