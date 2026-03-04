set -u
cd /repo
echo "=== SKILL file search under /repo (permission errors ignored) ==="
find . -type f -name "SKILL.md"   -print 2>/dev/null | sort
find . -type f -name "SKILLS.MD"  -print 2>/dev/null | sort