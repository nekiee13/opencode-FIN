# End-to-End Pipeline

## Stage Contract

The OC workflow follows a five-stage evidence model.

1. Retrieval
2. Planning and preflight
3. Approval
4. Edit
5. Test and result

Evidence contract source: `docs/integration-pilot/epic-4-workflow-artifact-spec.md`

## Pipeline Diagram

```mermaid
flowchart TD
    A[User Request] --> B[Retrieve Code Context via jCodeMunch]
    B --> C[Retrieve Docs Context via jDocMunch]
    C --> D[Preflight with Superpowers Skills]
    D --> E{Preflight Pass?}

    E -- No --> E1[Stop and report missing preflight evidence]
    E1 --> Z[Run marked failed]

    E -- Yes --> F[OAC Approval Gate]
    F --> G{Approval Granted?}

    G -- No --> G1[Stop and record gate denial]
    G1 --> Z

    G -- Yes --> H[Edit via Serena]
    H --> I{Edit Success?}

    I -- No --> I1[Capture edit failure and return to repair]
    I1 --> Z

    I -- Yes --> J[Run Verification Command]
    J --> K{Tests Pass?}

    K -- No --> K1[Record failure and block completion]
    K1 --> Z

    K -- Yes --> L[Publish Stage Artifact Report]
    L --> M[Workflow Completed]
```

## Failure Boundary Rules

- Missing retrieval evidence blocks transition into planning.
- Preflight failure blocks gate request.
- Approval denial blocks all edit actions.
- Edit failure blocks test stage.
- Test failure blocks completion artifact.

Control authority source: `docs/integration-pilot/adr/0003-control-plane-authority-hierarchy.md`
