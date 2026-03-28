# OpenCode (OC) Documentation Set

## Scope

This documentation set covers only the OpenCode stack in this repository.

Included scope:

- `.opencode` runtime configuration and plugin wiring
- `tools/hello-stack` bootstrap and stack checks
- `docs/integration-pilot` operational evidence
- `vendor/OpenAgentsControl` payload elements used by OC

Excluded scope:

- Forecasting and finance implementation in `src/`, `compat/`, and `scripts/`

## Generated Artifacts

- Inventory: `docs/oc/generated/oc_inventory.json`
- Class and entity index: `docs/oc/generated/oc_class_index.json`
- Entity mirror output: `docs/oc/generated/oc_entities.json`
- Invalid-file skip log: `docs/oc/generated/skipped_invalid_files.json`
- Entity catalog: `docs/oc/entities/entity_catalog.md`
- Entity dataclasses: `docs/oc/entities/entity_dataclasses.py`

## Required Deliverables

- Architecture diagram (Mermaid): `docs/oc/architecture/architecture_diagram.mmd`
- Module and class design: `docs/oc/design/module_class_design.md`
- Dataclasses for entities: `docs/oc/entities/entity_dataclasses.py`
- End-to-end pipeline diagram (Mermaid): `docs/oc/pipeline/end_to_end_pipeline.mmd`
- Class relationship diagram (Mermaid UML): `docs/oc/uml/class_relationships.mmd`
- UML sequence diagram (Mermaid): `docs/oc/uml/sequence_flow.mmd`
- Software Specification (SwS): `docs/oc/sws/software_specification.md`

## Build Command

```bash
python3 tools/oc_docs/build_oc_docs.py
```

The build script enforces the invalid-file skip policy:

- If an invalid payload pattern is detected (`{"type":"error" ... "type":"invalid...`), the file is skipped.
- Skipped files are recorded in `docs/oc/generated/skipped_invalid_files.json`.
