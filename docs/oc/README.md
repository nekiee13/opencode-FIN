# OpenCode (OC) Documentation Set

Last reviewed: 2026-04-11
Source commit: `055c7bc`

## Scope

This documentation set covers only the OpenCode stack in this repository.

Included:

- `.opencode` runtime configuration and plugin wiring
- `tools/hello-stack` bootstrap and stack checks
- `docs/integration-pilot` evidence references (pilot context)
- `vendor/OpenAgentsControl` payload elements consumed by OC docs

Excluded:

- Forecasting/finance implementation in `src/`, `compat/`, and `scripts/`

## Generated Artifacts (Snapshot Class)

- `docs/oc/generated/oc_inventory.json`
- `docs/oc/generated/oc_class_index.json`
- `docs/oc/generated/oc_entities.json`
- `docs/oc/generated/skipped_invalid_files.json`

Generated files are snapshots and must be refreshed by rebuilding OC docs after relevant source changes.

## Required Deliverables

- Architecture diagram: `docs/oc/architecture/architecture_diagram.mmd`
- Module and class design: `docs/oc/design/module_class_design.md`
- Entity catalog: `docs/oc/entities/entity_catalog.md`
- Dataclasses: `docs/oc/entities/entity_dataclasses.py`
- End-to-end pipeline diagram: `docs/oc/pipeline/end_to_end_pipeline.mmd`
- Class relationship diagram: `docs/oc/uml/class_relationships.mmd`
- UML sequence diagram: `docs/oc/uml/sequence_flow.mmd`
- Software specification: `docs/oc/sws/software_specification.md`

## Build Command

```bash
python3 tools/oc_docs/build_oc_docs.py
```

Build policy:

- Invalid payload patterns are skipped.
- Skipped files are logged in `docs/oc/generated/skipped_invalid_files.json`.
