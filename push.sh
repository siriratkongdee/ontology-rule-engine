#!/bin/bash
# Push ontology-rule-engine to GitHub
# Run this once from your Mac Terminal to push any changes

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "📁 Working in: $REPO_DIR"
echo ""

# Check if remote is set
if ! git remote get-url origin &>/dev/null; then
  git remote add origin https://github.com/siriratkongdee/ontology-rule-engine.git
fi

git remote set-url origin https://github.com/siriratkongdee/ontology-rule-engine.git

# Stage any new/changed files
git add -A

# Show what's staged
echo "📋 Changes to push:"
git status --short
echo ""

# Commit if there are changes
if ! git diff --cached --quiet; then
  read -p "Commit message (or press Enter for default): " MSG
  MSG="${MSG:-Update rule engine}"
  git commit -m "$MSG"
fi

# Push
echo "🚀 Pushing to GitHub..."
git push -u origin main

echo ""
echo "✅ Done! Check: https://github.com/siriratkongdee/ontology-rule-engine"
