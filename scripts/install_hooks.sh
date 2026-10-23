#!/usr/bin/env bash
# Install the local CI git hooks (git does not version .git/hooks, so this script is committed instead).
# Run once after cloning, from the project root:  bash scripts/install_hooks.sh
set -euo pipefail

# DVC's own hooks: status on commit, checkout on branch switch, push on git push (skipped if already installed)
[ -f .git/hooks/post-checkout ] || dvc install

cat > .git/hooks/pre-commit <<'HOOK'
#!/bin/sh
# FilingLens CI gate: the lint and test DVC stages must pass before a commit is accepted.
# DVC reruns them only when code changed since the last passing run, so unchanged commits are instant.
dvc repro lint test || {
    echo "CI failed: commit blocked. See reports/lint_report.txt or the pytest output above."
    exit 1
}
git add dvc.lock reports/lint_report.txt reports/pytest_results.xml reports/test_summary.md reports/test_summary.json
exec dvc git-hook pre-commit "$@"
HOOK
chmod +x .git/hooks/pre-commit
echo "CI hooks installed: lint and tests now run on every commit."
