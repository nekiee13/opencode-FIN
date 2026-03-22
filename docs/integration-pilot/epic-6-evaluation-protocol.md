# Epic 6.1 Evaluation Protocol and Thresholds

Date: 2026-03-22
Status: frozen before Task 6.2 runs

## Benchmark set freeze

Benchmark set is frozen to the Epic 0 set with no additions:

- `B1` runtime reaches usable model-backed state
- `B2` stack retrieval wiring is operational
- `B3` hello-stack wiring and targeted test readiness signal

Reference baseline:

- `docs/integration-pilot/epic-0-benchmark-baseline.md`

## Comparison rules

- Use the same benchmark IDs and command families as Epic 0.
- Compare outcome metrics first, process metrics second.
- For each benchmark, report:
  - total time to completed check
  - failed-result count
  - rework cycles
  - final test outcome quality

## Thresholds (finalized before Task 6.2)

### Primary thresholds

1. Completion-time regression tolerance:
   - `B2` and `B3` command timings must not regress by more than `25%` versus baseline.
2. Defect-count non-regression:
   - `B1` and `B2` failed-result count must not increase above baseline.
3. Minimum improvement signal:
   - At least one benchmark must show meaningful quality or efficiency improvement.
   - In this pilot, acceptable improvement signals are:
     - improved final test outcome quality evidence for `B1` (stronger verified gate coverage), or
     - reduced failed-result count, or
     - reduced rework cycles, or
     - improved completion time without quality regression.

### Decision use

- If a benchmark exceeds threshold, result must be linked to one of:
  - remediation
  - deferral
  - rejection
  - partial-adoption recommendation

## Attribution note

Where practical, improvements/regressions are tagged by likely primary contributor:

- retrieval (`jCodeMunch` / `jDocMunch`)
- editing (`Serena`)
- behavioral discipline (Superpowers)
- orchestration/gating (OAC)
