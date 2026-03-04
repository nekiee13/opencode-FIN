set -u
echo "=== Container ==="
hostname || true
id || true
echo

echo "=== Key paths existence ==="
for p in /repo /workspace /home/opencode /home/opencode/.config/opencode /home/opencode/.local/share/opencode /workspace/.config/opencode; do
  if [ -e "$p" ]; then echo "EXISTS $p"; else echo "MISSING $p"; fi
done
echo

echo "=== opencode.jsonc candidates (first 30 lines each) ==="
for p in \
  /workspace/.config/opencode/opencode.jsonc \
  /home/opencode/.config/opencode/opencode.jsonc \
  /repo/opencode.jsonc \
  /repo/.opencode/opencode.jsonc
do
  if [ -f "$p" ]; then
    echo "--- $p"
    sed -n '1,30p' "$p" 2>/dev/null || true
    echo
  fi
done

echo "=== Grep for 'agent'/'agents'/'sub-agent' in config files ==="
for p in \
  /workspace/.config/opencode/opencode.jsonc \
  /home/opencode/.config/opencode/opencode.jsonc \
  /repo/opencode.jsonc \
  /repo/.opencode/opencode.jsonc
do
  if [ -f "$p" ]; then
    echo "--- $p"
    grep -n -i -E 'agent|agents|sub-?agent' "$p" 2>/dev/null || true
    echo
  fi
done

echo "=== Repo scan: likely agent definition files (names/paths) ==="
# common patterns across agent frameworks
find /repo -type f 2>/dev/null | grep -E -i \
'(/agents?/|agent(s)?\.(ya?ml|json|jsonc|toml|md)$|system\.md$|prompt(s)?\.(md|txt)$|\.opencode/|\.claude/|\.agents/)' \
| head -n 400 || true
echo

echo "=== Repo scan: content markers inside text configs (first hits) ==="
# scan only small-ish text-like files for markers
find /repo -type f 2>/dev/null | grep -E -i '\.(md|txt|ya?ml|json|jsonc|toml)$' | head -n 2000 \
| while read -r f; do
    grep -n -i -E 'agent|agents|sub-?agent|role:|system:|tool(s)?:|mcp' "$f" 2>/dev/null | head -n 3 | sed "s|^|$f:|"
  done | head -n 250 || true
echo

echo "=== OpenCode persisted state: likely agent/session registries ==="
# list storage roots without dumping sensitive contents
for p in \
  /home/opencode/.local/share/opencode/storage \
  /home/opencode/.local/state/opencode \
  /home/opencode/.config/opencode
do
  if [ -d "$p" ]; then
    echo "--- $p (top level)"
    ls -la "$p" 2>/dev/null || true
    echo
  fi
done

echo "=== MCP config presence ==="
for p in \
  /workspace/.config/opencode/opencode.jsonc \
  /home/opencode/.config/opencode/opencode.jsonc
do
  if [ -f "$p" ]; then
    echo "--- $p (mcp lines)"
    grep -n -i -E 'mcp|serena' "$p" 2>/dev/null || true
    echo
  fi
done