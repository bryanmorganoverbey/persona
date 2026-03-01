"""
Category Scanner — reads all persona preference categories and measures
their depth/sparseness to guide question generation.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".github", "scripts", "vision_boards", "docs", "node_modules"}


@dataclass
class CategoryFile:
    path: str
    name: str
    word_count: int


@dataclass
class Category:
    name: str
    directory: str
    description: str
    files: list[CategoryFile] = field(default_factory=list)
    total_words: int = 0

    @property
    def is_sparse(self) -> bool:
        return len(self.files) <= 2 or self.total_words < 300


def read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def extract_description(index_content: str) -> str:
    """Extract the description from index.md (first non-frontmatter, non-H1 line)."""
    in_frontmatter = False
    for line in index_content.split("\n"):
        stripped = line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if stripped.startswith("# "):
            continue
        if stripped:
            return stripped
    return ""


def count_words(text: str) -> int:
    return len(text.split())


def scan_categories(repo_root: str) -> list[Category]:
    """
    Scan all top-level directories in the repo for persona categories.
    A category is any directory with an index.md that isn't in SKIP_DIRS.
    """
    root = Path(repo_root)
    categories = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue

        index_path = entry / "index.md"
        if not index_path.exists():
            continue

        index_content = read_file_safe(index_path)
        description = extract_description(index_content)

        cat = Category(
            name=entry.name,
            directory=str(entry),
            description=description,
        )

        # Collect all markdown files in the category
        for md_file in sorted(entry.rglob("*.md")):
            content = read_file_safe(md_file)
            wc = count_words(content)
            cat.files.append(CategoryFile(
                path=str(md_file),
                name=md_file.relative_to(entry).as_posix(),
                word_count=wc,
            ))
            cat.total_words += wc

        categories.append(cat)

    return categories


def build_category_summary(categories: list[Category]) -> str:
    """Build a text summary of all categories and their depth for the LLM."""
    lines = []
    for cat in sorted(categories, key=lambda c: c.total_words):
        sparse_tag = " [SPARSE]" if cat.is_sparse else ""
        lines.append(
            f"- **{cat.name}**{sparse_tag}: {cat.description} "
            f"({len(cat.files)} files, {cat.total_words} words)"
        )
        for f in cat.files:
            lines.append(f"  - {f.name} ({f.word_count} words)")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    repo_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    cats = scan_categories(repo_root)

    print(f"Found {len(cats)} categories:\n")
    print(build_category_summary(cats))

    sparse = [c for c in cats if c.is_sparse]
    print(f"\nSparse categories ({len(sparse)}):")
    for c in sparse:
        print(f"  {c.name}: {len(c.files)} files, {c.total_words} words")
