set -eu
cd /repo
echo "PWD:"
pwd
echo

echo "=== vendor top (ls -la) ==="
if [ -d vendor ]; then
  ls -la vendor
else
  echo "vendor/ missing"
  exit 0
fi
echo

echo "=== vendor depth=2 (directories) ==="
find vendor -maxdepth 2 -mindepth 1 -type d -print | sort
echo

echo "=== vendor depth=2 (files) ==="
find vendor -maxdepth 2 -mindepth 1 -type f -print | sort
echo

echo "=== git probes (if vendor items are git repos) ==="
for d in vendor/*; do
  [ -d "$d" ] || continue
  if [ -d "$d/.git" ]; then
    echo "--- $d"
    git -C "$d" status -sb || true
    git -C "$d" log -1 --oneline || true
  fi
done