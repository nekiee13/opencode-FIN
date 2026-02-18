# ------------------------
# tools\ownership_map.py
# ------------------------
import ast
import json
from pathlib import Path

REPO_ROOT = Path(".").resolve()
OUT_JSON = Path("out/ownership_map.json")

def iter_py_files(root):
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p

def find_compat_functions(repo_root):
    results = []
    compat_dir = repo_root / "compat"
    if not compat_dir.exists():
        return results

    for py in iter_py_files(compat_dir):
        src = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                results.append({
                    "module": str(py.relative_to(repo_root)),
                    "function": node.name,
                    "lineno": node.lineno,
                })
    return results

def find_entrypoints(repo_root):
    eps = []
    for py in iter_py_files(repo_root):
        src = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                try:
                    if (
                        isinstance(node.test, ast.Compare)
                        and isinstance(node.test.left, ast.Name)
                        and node.test.left.id == "__name__"
                    ):
                        eps.append({
                            "file": str(py.relative_to(repo_root)),
                            "lineno": node.lineno,
                        })
                except Exception:
                    pass
    return eps

def main():
    data = {
        "repo_root": str(REPO_ROOT),
        "compat_functions": find_compat_functions(REPO_ROOT),
        "entrypoints": find_entrypoints(REPO_ROOT),
    }
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")

if __name__ == "__main__":
    main()
