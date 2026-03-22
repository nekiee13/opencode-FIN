# Epic 4.2 Workflow Artifact Specification

Date: 2026-03-22
Scope: pilot hello-stack workflow

## Stage model

Workflow stages are fixed:

1. retrieval
2. planning/preflight
3. approval
4. edit
5. test/result

Stage advancement is evidence-based. Missing required evidence blocks transition.

## Minimum required evidence by stage

### 1) Retrieval

Required evidence:

- code retrieval reference (symbol/file id, path, or equivalent)
- docs retrieval reference (section id/path or equivalent)
- retrieval timestamps

Blocks advancement when:

- either code or docs reference is missing
- retrieval output is not traceable to a source

### 2) Planning/Preflight

Required evidence:

- concise execution plan tied to retrieved references
- preflight checklist result covering:
  - required skills visibility
  - selected edit target
  - selected verification command

Blocks advancement when:

- plan has no linkage to retrieval artifacts
- preflight checklist contains unresolved fail items

### 3) Approval

Required evidence:

- approval record for transition `preflight -> edit`
- gate decision (`approved` or `denied`)
- decision rationale or missing requirement note

Blocks advancement when:

- approval record is absent
- decision is `denied`

### 4) Edit

Required evidence:

- edit summary with target path and operation
- edit result status (`success` or `failed`)
- failure detail if status is `failed`

Blocks advancement when:

- edit status is `failed`
- edit summary is missing

### 5) Test/Result

Required evidence:

- exact test/verification command run
- pass/fail result output
- final stage outcome (`completed` or `failed`)

Blocks completion when:

- result artifact is missing
- command output cannot be tied to the edited target

## Artifact format rule

- A single run report may hold all stage evidence.
- Each stage must be represented by a dedicated section with explicit status.
- If a stage fails, failure boundary must be stated as `stageA -> stageB`.
