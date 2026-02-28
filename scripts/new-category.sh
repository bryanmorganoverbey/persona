#!/usr/bin/env bash
#
# Create a new preference category with the standard structure.
#
# Usage: ./scripts/new-category.sh <category-name> "<description>"
# Example: ./scripts/new-category.sh hobbies "Hobbies and leisure activities"

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <category-name> \"<description>\""
  echo "Example: $0 hobbies \"Hobbies and leisure activities\""
  exit 1
fi

CATEGORY="$1"
DESCRIPTION="$2"
DIR="$(cd "$(dirname "$0")/.." && pwd)/${CATEGORY}"
TODAY=$(date +%Y-%m-%d)

if [ -d "$DIR" ]; then
  echo "Error: Category '${CATEGORY}' already exists at ${DIR}"
  exit 1
fi

mkdir -p "$DIR"

# Create index.md
cat > "${DIR}/index.md" << EOF
# $(echo "$CATEGORY" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)}1')

${DESCRIPTION}

## Related Categories

<!-- Add links to related categories here -->

## Files

| File | Description |
|------|-------------|
EOF

echo "Created ${DIR}/index.md"
echo ""
echo "Next steps:"
echo "  1. Add content files to ${DIR}/ with frontmatter:"
echo "     ---"
echo "     last_reviewed: ${TODAY}"
echo "     confidence: high"
echo "     ---"
echo "  2. Update the Files table in ${DIR}/index.md"
echo "  3. Add the category to README.md (or run: ./scripts/generate-toc.sh)"
echo "  4. Add cross-references to related categories"
