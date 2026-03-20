#!/usr/bin/env bash
# Cleanup script for stale/junk branches and PRs
# Generated: 2026-03-20
#
# Identified junk branches:
#   - claude/debug-improvements-GAs3B
#     105 files changed, mostly bulk deletion of test files and frontend components.
#     No associated merged PR. Appears to be an abandoned Claude-generated branch.
#
# Usage: Run this script from the repo root with appropriate permissions.

set -euo pipefail

REMOTE="${1:-origin}"

echo "=== Stale Branch Cleanup ==="

JUNK_BRANCHES=(
  "claude/debug-improvements-GAs3B"
)

for branch in "${JUNK_BRANCHES[@]}"; do
  echo "Deleting remote branch: $branch"
  if git push "$REMOTE" --delete "$branch" 2>/dev/null; then
    echo "  ✓ Deleted $branch"
  else
    echo "  ✗ Failed to delete $branch (may already be deleted or insufficient permissions)"
  fi
done

# Also prune stale remote-tracking references
echo ""
echo "Pruning stale remote-tracking references..."
git remote prune "$REMOTE"

echo ""
echo "Remaining remote branches:"
git ls-remote --heads "$REMOTE"

echo ""
echo "Done."
