"""Build a sanitized release ZIP from the project tree."""

from __future__ import annotations

import argparse
import re
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENIED_DIRS = {
    ".git",
    ".venv",
    ".harness",
    ".claude",
    ".codex",
    ".cursor",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "logs",
    "output",
    "outputs",
    "exports",
}
DENIED_FILES = {
    ".env",
    ".mcp.json",
    ".cursorrules",
    "AGENTS.md",
    "CLAUDE.md",
    "HARNESS_SETUP.md",
    "context.txt",
    "updatedcontext.md",
    "log.md",
}
DENIED_SUFFIXES = {".pyc", ".pyo", ".log", ".cdr", ".zip"}
DENIED_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/]+[\\/]"),
    re.compile(r"python3\.14\.3[\\/]python(?:\.exe)?"),
    re.compile(r"coreldraw-mcp-0\.1\.0[\\/]server"),
)


def ignore(directory: str, names: list[str]) -> list[str]:
    ignored: list[str] = []
    for name in names:
        path = Path(directory) / name
        if name in DENIED_DIRS or name in DENIED_FILES or path.suffix.lower() in DENIED_SUFFIXES:
            ignored.append(name)
    return ignored


def validate_release(tree: Path) -> None:
    for path in tree.rglob("*"):
        if path.is_dir() and path.name in DENIED_DIRS:
            raise RuntimeError(f"Denied directory in release: {path}")
        if not path.is_file():
            continue
        if path.name in DENIED_FILES or path.suffix.lower() in DENIED_SUFFIXES:
            raise RuntimeError(f"Denied file in release: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in DENIED_PATTERNS:
            if pattern.search(text):
                raise RuntimeError(f"Machine-specific path in {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a sanitized CorelDRAW Live MCP release")
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    args = parser.parse_args()

    with (ROOT / "pyproject.toml").open("rb") as file:
        version = tomllib.load(file)["project"]["version"]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    release_name = f"coreldraw-mcp-{version}"
    release_tree = args.output_dir / release_name
    archive = args.output_dir / f"{release_name}.zip"
    shutil.rmtree(release_tree, ignore_errors=True)
    archive.unlink(missing_ok=True)

    shutil.copytree(ROOT, release_tree, ignore=ignore)
    validate_release(release_tree)
    shutil.make_archive(str(archive.with_suffix("")), "zip", args.output_dir, release_name)
    print(archive)


if __name__ == "__main__":
    main()
