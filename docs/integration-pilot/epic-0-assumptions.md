# Epic 0 Assumption Snapshot

Date: 2026-03-22

Flat list of major claims currently tracked as verified, unverified, or blocked.

- [verified] Deterministic startup order can reach a healthy OpenCode runtime when gates are passed in sequence. Validation task: Epic 0.4 benchmark capture.
- [verified] OpenCode model registry currently exposes both `openai/...codex` and `llamacpp/...` entries in the active runtime. Validation task: Epic 0.4 benchmark capture.
- [unverified] OAC payload can enforce approval/gating transitions in this environment. Expected validator: Epic 2.1, Epic 2.4, Epic 4.5.
- [unverified] OAC payload includes complete operational artifacts for selected target version. Expected validator: Epic 2.3 and Epic 2.5.
- [unverified] Superpowers startup injection executes once per fresh session without duplication. Expected validator: Epic 3.3.
- [unverified] Required Superpowers skill categories are discoverable in pilot runtime. Expected validator: Epic 3.3.
- [unverified] Config precedence between global and project-local settings is deterministic under repeated fresh starts. Expected validator: Epic 1.3.
- [unverified] Diagnostic bundle procedure can classify failures into workspace/config/stale-session/runtime-conflict classes within five minutes. Expected validator: Epic 1.4.
- [blocked] Exact OAC feature availability by version may not be recoverable from available docs in bounded effort. Expected validator: Epic 2.1 fallback rule (latest stable/tagged commit + recorded doc gap risk).
