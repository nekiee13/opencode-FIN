set -eu
echo "=== which opencode ==="
command -v opencode || true
p="$(command -v opencode 2>/dev/null || true)"

echo
echo "=== resolve symlink (ls -la) ==="
if [ -n "${p:-}" ]; then
  ls -la "$p" || true
fi

echo
echo "=== show wrapper (head -n 80) ==="
if [ -n "${p:-}" ]; then
  head -n 80 "$p" 2>/dev/null || true
fi

echo
echo "=== node module directory (ls -la) ==="
if [ -n "${p:-}" ]; then
  d="$(dirname "$p")"
  ls -la "$d" 2>/dev/null || true
fi