set -eu
cd /repo
echo "=== SKILL file search under /repo ==="
# Avoid shell-escape edge cases by using multiple -name tests without parentheses
find . -type f -name "SKILL.md" -print | sort
find . -type f -name "SKILLS.MD" -print | sort