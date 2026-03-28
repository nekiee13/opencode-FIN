#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCOPE_PATHS = [
    ".opencode",
    "tools/hello-stack",
    "docs/integration-pilot",
    "vendor/OpenAgentsControl/.opencode",
    "vendor/OpenAgentsControl/packages/plugin-abilities/src",
    "vendor/OpenAgentsControl/evals/framework/src",
    "vendor/OpenAgentsControl/registry.json",
    "vendor/OpenAgentsControl/README.md",
]

SKIP_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
}

TARGET_EXTENSIONS = {
    ".py",
    ".ts",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".sh",
    ".cjs",
    ".cts",
    ".js",
}


@dataclass
class SkippedFile:
    path: str
    reason: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skip_due_to_invalid_error(content: str) -> bool:
    compact = content.strip().replace(" ", "")
    if compact.startswith('{"type":"error"') and '"type":"invalid' in compact:
        return True
    return False


def _iter_scope_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in SCOPE_PATHS:
        abs_path = root / rel
        if not abs_path.exists():
            continue
        if abs_path.is_file():
            files.append(abs_path)
            continue
        for file_path in abs_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in SKIP_PARTS for part in file_path.parts):
                continue
            if file_path.suffix.lower() not in TARGET_EXTENSIONS:
                continue
            files.append(file_path)
    return sorted(set(files))


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _python_entities(path: Path, source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    dataclasses: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        decorators = [_decorator_name(d) for d in node.decorator_list]
        bases = [
            getattr(base, "id", None)
            or getattr(base, "attr", None)
            or ast.unparse(base)
            for base in node.bases
        ]

        class_record = {
            "name": node.name,
            "path": str(path),
            "line": node.lineno,
            "decorators": [d for d in decorators if d],
            "bases": [b for b in bases if b],
        }
        classes.append(class_record)

        if "dataclass" not in decorators:
            continue

        fields: list[dict[str, Any]] = []
        for body_node in node.body:
            if isinstance(body_node, ast.AnnAssign) and isinstance(
                body_node.target, ast.Name
            ):
                annotation = ast.unparse(body_node.annotation)
                fields.append(
                    {
                        "name": body_node.target.id,
                        "type": annotation,
                        "has_default": body_node.value is not None,
                    }
                )

        dataclasses.append(
            {
                "name": node.name,
                "path": str(path),
                "line": node.lineno,
                "fields": fields,
            }
        )

    return {
        "python_dataclasses": dataclasses,
        "python_classes": classes,
    }


INTERFACE_RE = re.compile(
    r"^\s*(?:export\s+)?interface\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\{(?P<body>.*?)^\s*\}",
    re.DOTALL | re.MULTILINE,
)
INTERFACE_FIELD_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\??:\s*(?P<type>[^;]+);",
    re.MULTILINE,
)
TYPE_RE = re.compile(
    r"^\s*(?:export\s+)?type\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^;]+);",
    re.MULTILINE,
)
CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+(?P<extends>[A-Za-z_][A-Za-z0-9_]*))?(?:\s+implements\s+(?P<implements>[^\{]+))?",
    re.MULTILINE,
)


def _typescript_entities(path: Path, source: str) -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    types: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []

    for match in INTERFACE_RE.finditer(source):
        fields = []
        for field in INTERFACE_FIELD_RE.finditer(match.group("body")):
            fields.append(
                {
                    "name": field.group("name"),
                    "type": field.group("type").strip(),
                }
            )
        interfaces.append(
            {
                "name": match.group("name"),
                "path": str(path),
                "fields": fields,
            }
        )

    for match in TYPE_RE.finditer(source):
        types.append(
            {
                "name": match.group("name"),
                "path": str(path),
                "value": match.group("value").strip(),
            }
        )

    for match in CLASS_RE.finditer(source):
        implemented = []
        impl = match.group("implements")
        if impl:
            implemented = [item.strip() for item in impl.split(",") if item.strip()]
        classes.append(
            {
                "name": match.group("name"),
                "path": str(path),
                "extends": match.group("extends") or "",
                "implements": implemented,
            }
        )

    return {
        "ts_interfaces": interfaces,
        "ts_types": types,
        "ts_classes": classes,
    }


def _merge_entities(
    target: dict[str, list[dict[str, Any]]], update: dict[str, Any]
) -> None:
    for key, value in update.items():
        if key not in target:
            target[key] = []
        target[key].extend(value)


def _to_pascal_case(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    clean = [part for part in parts if part]
    if not clean:
        return "Entity"
    return "".join(piece[:1].upper() + piece[1:] for piece in clean)


def _unique_name(base: str, seen: set[str]) -> str:
    if base not in seen:
        seen.add(base)
        return base
    index = 2
    while f"{base}{index}" in seen:
        index += 1
    unique = f"{base}{index}"
    seen.add(unique)
    return unique


def _registry_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    components = data.get("components", {})

    counts: dict[str, int] = {}
    dependency_edges = 0
    for name, payload in components.items():
        if isinstance(payload, list):
            counts[name] = len(payload)
            for item in payload:
                deps = item.get("dependencies", [])
                if isinstance(deps, list):
                    dependency_edges += len(deps)
        else:
            counts[name] = 0

    return {
        "path": str(path),
        "version": data.get("version"),
        "schema_version": data.get("schema_version"),
        "component_counts": counts,
        "dependency_edges": dependency_edges,
    }


def build(root: Path) -> None:
    out_dir = root / "docs" / "oc" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    entities_dir = root / "docs" / "oc" / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    files = _iter_scope_files(root)
    skipped: list[SkippedFile] = []
    entities: dict[str, list[dict[str, Any]]] = {
        "python_dataclasses": [],
        "python_classes": [],
        "ts_interfaces": [],
        "ts_types": [],
        "ts_classes": [],
    }

    file_counts_by_scope: dict[str, int] = {scope: 0 for scope in SCOPE_PATHS}
    extension_counts: dict[str, int] = {}

    for file_path in files:
        rel = file_path.relative_to(root).as_posix()

        for scope in SCOPE_PATHS:
            if rel == scope or rel.startswith(f"{scope}/"):
                file_counts_by_scope[scope] += 1
                break

        ext = file_path.suffix.lower() or "<noext>"
        extension_counts[ext] = extension_counts.get(ext, 0) + 1

        try:
            content = _safe_read_text(file_path)
        except UnicodeDecodeError as exc:
            skipped.append(SkippedFile(path=rel, reason=f"encoding_error:{exc}"))
            continue
        except OSError as exc:
            skipped.append(SkippedFile(path=rel, reason=f"io_error:{exc}"))
            continue

        if _skip_due_to_invalid_error(content):
            skipped.append(
                SkippedFile(path=rel, reason="invalid_error_payload_detected")
            )
            continue

        try:
            if file_path.suffix.lower() == ".py":
                _merge_entities(entities, _python_entities(Path(rel), content))
            elif file_path.suffix.lower() == ".ts":
                _merge_entities(entities, _typescript_entities(Path(rel), content))
            elif file_path.suffix.lower() == ".json":
                json.loads(content)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if "invalid" in text.lower():
                skipped.append(SkippedFile(path=rel, reason=f"invalid_parse:{text}"))

    registry = _registry_summary(
        root / "vendor" / "OpenAgentsControl" / "registry.json"
    )

    inventory = {
        "generated_at": _utc_now(),
        "root": str(root),
        "scope_paths": SCOPE_PATHS,
        "total_files_in_scope": len(files),
        "file_counts_by_scope": file_counts_by_scope,
        "extension_counts": dict(sorted(extension_counts.items())),
        "registry_summary": registry,
    }

    class_index = {
        "generated_at": _utc_now(),
        "python_class_count": len(entities["python_classes"]),
        "python_dataclass_count": len(entities["python_dataclasses"]),
        "ts_class_count": len(entities["ts_classes"]),
        "ts_interface_count": len(entities["ts_interfaces"]),
        "ts_type_count": len(entities["ts_types"]),
        "python_classes": sorted(
            entities["python_classes"], key=lambda item: (item["path"], item["name"])
        ),
        "python_dataclasses": sorted(
            entities["python_dataclasses"],
            key=lambda item: (item["path"], item["name"]),
        ),
        "ts_classes": sorted(
            entities["ts_classes"], key=lambda item: (item["path"], item["name"])
        ),
        "ts_interfaces": sorted(
            entities["ts_interfaces"], key=lambda item: (item["path"], item["name"])
        ),
        "ts_types": sorted(
            entities["ts_types"], key=lambda item: (item["path"], item["name"])
        ),
    }

    skipped_payload = {
        "generated_at": _utc_now(),
        "skip_policy": "skip file when invalid error payload or invalid parse error is detected",
        "skipped_count": len(skipped),
        "skipped_files": [
            {"path": item.path, "reason": item.reason}
            for item in sorted(skipped, key=lambda s: s.path)
        ],
    }

    (out_dir / "oc_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "oc_class_index.json").write_text(
        json.dumps(class_index, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "oc_entities.json").write_text(
        json.dumps(class_index, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "skipped_invalid_files.json").write_text(
        json.dumps(skipped_payload, indent=2) + "\n", encoding="utf-8"
    )

    catalog_lines: list[str] = []
    catalog_lines.append("# OC Entity Catalog")
    catalog_lines.append("")
    catalog_lines.append(f"Generated at: {_utc_now()}")
    catalog_lines.append("")
    catalog_lines.append("## Python Dataclasses")
    catalog_lines.append("")
    if class_index["python_dataclasses"]:
        for item in class_index["python_dataclasses"]:
            catalog_lines.append(f"### {item['name']}")
            catalog_lines.append(f"Source: `{item['path']}:{item['line']}`")
            catalog_lines.append("")
            catalog_lines.append("| Field | Type | Default |")
            catalog_lines.append("| --- | --- | --- |")
            for field in item["fields"]:
                has_default = "yes" if field["has_default"] else "no"
                catalog_lines.append(
                    f"| `{field['name']}` | `{field['type']}` | {has_default} |"
                )
            catalog_lines.append("")
    else:
        catalog_lines.append("No Python dataclasses detected in scope.")
        catalog_lines.append("")

    catalog_lines.append("## TypeScript Interfaces")
    catalog_lines.append("")
    catalog_lines.append("| Interface | Fields | Source |")
    catalog_lines.append("| --- | ---: | --- |")
    for item in class_index["ts_interfaces"]:
        catalog_lines.append(
            f"| `{item['name']}` | {len(item['fields'])} | `{item['path']}` |"
        )
    catalog_lines.append("")

    catalog_lines.append("## TypeScript Type Aliases")
    catalog_lines.append("")
    catalog_lines.append("| Type | Source |")
    catalog_lines.append("| --- | --- |")
    for item in class_index["ts_types"]:
        catalog_lines.append(f"| `{item['name']}` | `{item['path']}` |")
    catalog_lines.append("")

    catalog_lines.append("## TypeScript Classes")
    catalog_lines.append("")
    catalog_lines.append("| Class | Extends | Implements | Source |")
    catalog_lines.append("| --- | --- | --- | --- |")
    for item in class_index["ts_classes"]:
        impl = ", ".join(item["implements"]) if item["implements"] else "-"
        ext = item["extends"] if item["extends"] else "-"
        catalog_lines.append(
            f"| `{item['name']}` | `{ext}` | `{impl}` | `{item['path']}` |"
        )
    catalog_lines.append("")

    (entities_dir / "entity_catalog.md").write_text(
        "\n".join(catalog_lines) + "\n", encoding="utf-8"
    )

    dataclass_lines: list[str] = []
    dataclass_lines.append("from __future__ import annotations")
    dataclass_lines.append("")
    dataclass_lines.append("from dataclasses import dataclass")
    dataclass_lines.append("from typing import Any")
    dataclass_lines.append("")
    dataclass_lines.append('"""Generated OC entity dataclasses.')
    dataclass_lines.append("")
    dataclass_lines.append("Each dataclass mirrors an entity discovered in OC scope.")
    dataclass_lines.append("TypeScript entities are mapped to Any for portability.")
    dataclass_lines.append('"""')
    dataclass_lines.append("")

    used_names: set[str] = set()

    for item in class_index["python_dataclasses"]:
        class_name = _unique_name(_to_pascal_case(item["name"]), used_names)
        dataclass_lines.append("@dataclass")
        dataclass_lines.append(f"class {class_name}:")
        dataclass_lines.append(f'    """Source: {item["path"]}:{item["line"]}"""')
        if item["fields"]:
            for field in item["fields"]:
                field_name = field["name"]
                field_type = field["type"] if field.get("type") else "Any"
                dataclass_lines.append(f"    {field_name}: {field_type}")
        else:
            dataclass_lines.append("    pass")
        dataclass_lines.append("")

    for item in class_index["ts_interfaces"]:
        source_stem = Path(item["path"]).stem
        base_name = _to_pascal_case(item["name"])
        suffix = _to_pascal_case(source_stem)
        class_name = _unique_name(f"{base_name}{suffix}", used_names)
        dataclass_lines.append("@dataclass")
        dataclass_lines.append(f"class {class_name}:")
        dataclass_lines.append(f'    """Source: {item["path"]}"""')
        if item["fields"]:
            for field in item["fields"]:
                field_name = re.sub(r"[^A-Za-z0-9_]", "_", field["name"])
                dataclass_lines.append(f"    {field_name}: Any = None")
        else:
            dataclass_lines.append("    data: Any = None")
        dataclass_lines.append("")

    (entities_dir / "entity_dataclasses.py").write_text(
        "\n".join(dataclass_lines), encoding="utf-8"
    )


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    build(root)
    print("OC documentation artifacts generated in docs/oc/generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
