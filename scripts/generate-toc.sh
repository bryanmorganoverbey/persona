#!/usr/bin/env bash
#
# Generate the Directory table in README.md from the actual folder structure.
# Reads each category's index.md for the description line.
#
# Usage: ./scripts/generate-toc.sh          # preview to stdout
#        ./scripts/generate-toc.sh --write  # update README.md in place

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
README="${REPO_ROOT}/README.md"
SKIP_DIRS="scripts .git .github vision_boards"
TABLE_FILE=$(mktemp)

{
  echo "| Folder | Description |"
  echo "|--------|-------------|"

  for dir in "$REPO_ROOT"/*/; do
    dirname=$(basename "$dir")

    skip=false
    for s in $SKIP_DIRS; do
      [ "$dirname" = "$s" ] && skip=true
    done
    $skip && continue

    index="${dir}index.md"
    [ ! -f "$index" ] && continue

    description=""
    in_frontmatter=false
    while IFS= read -r line; do
      if [ "$line" = "---" ] && [ "$in_frontmatter" = false ]; then
        in_frontmatter=true
        continue
      fi
      if [ "$line" = "---" ] && [ "$in_frontmatter" = true ]; then
        in_frontmatter=false
        continue
      fi
      $in_frontmatter && continue
      [ -z "$line" ] && continue
      [[ "$line" =~ ^#\  ]] && continue
      description="$line"
      break
    done < "$index"

    [ -z "$description" ] && description="(no description)"

    echo "| [${dirname}](./${dirname}/) | ${description} |"
  done
} > "$TABLE_FILE"

if [ "${1:-}" = "--write" ]; then
  # Build new README: everything before "## Directory", then table, then everything after next "##"
  {
    # Print lines up to and including "## Directory"
    sed -n '1,/^## Directory/p' "$README"
    echo ""
    cat "$TABLE_FILE"

    # Print lines from the next ## heading after Directory onward
    awk '
      BEGIN { found_dir=0; found_next=0 }
      /^## Directory/ { found_dir=1; next }
      found_dir && !found_next && /^## / { found_next=1 }
      found_next { print }
    ' "$README"
  } > "${README}.tmp"

  mv "${README}.tmp" "$README"
  rm "$TABLE_FILE"
  echo "Updated README.md directory table."
else
  cat "$TABLE_FILE"
  rm "$TABLE_FILE"
  echo ""
  echo "Run with --write to update README.md in place."
fi
