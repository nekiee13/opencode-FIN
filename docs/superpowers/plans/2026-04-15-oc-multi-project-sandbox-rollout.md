# OC Multi-Project Sandbox Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize a reusable OpenCode core stack and roll out six isolated project sandboxes (`FIN`, `Marker`, `LLM Wiki`, `JSON`, `Loto`, `Games`) with repeatable setup, strict isolation, and scalable onboarding for `P7+`.

**Architecture:** A golden-core repository (`opencode-agent-core`) provides versioned templates and automation. Each project runs in its own isolated runtime instance with project-local config, secrets, logs, state, and backups. Provisioning, upgrades, rollback, and restore validation are standardized and evidence-driven.

**Tech Stack:** OpenCode runtime, Superpowers skills, OAC integration, Serena MCP, jCodeMunch MCP, jDocMunch MCP, Docker Desktop, WSL2, GitHub Issues, GitHub Actions.

---

## Task 1: Core Repository Productization

**Files:**
- Create: `opencode-agent-core` repository baseline structure
- Create: core documentation (`README`, lifecycle, versioning/changelog)
- Create: core checks (`check_core_stack`)

- [ ] Create baseline repository structure (`templates/`, `scripts/`, `docs/`, `checks/`, `examples/`).
- [ ] Port OC runtime + MCP + skills/OAC templates (non-secret only).
- [ ] Remove FIN-specific paths and secret references.
- [ ] Add Win11 + WSL2 path translation guidance.
- [ ] Implement and verify `check_core_stack` with machine-readable output.

## Task 2: Sandbox Template and Lifecycle Automation

**Files:**
- Create: template contract docs
- Create: provisioning/update scripts
- Create: runtime metadata schema

- [ ] Define required runtime folder and env contract.
- [ ] Implement `create-sandbox` with dry-run support.
- [ ] Implement `update-sandbox` with pre-update snapshots.
- [ ] Implement drift detection (`CLEAN`, `DRIFTED`, `BLOCKED`).
- [ ] Implement rollback command/path.
- [ ] Implement `add-project` workflow for `P7+`.

## Task 3: Isolation and Security Enforcement

**Files:**
- Create: startup gate checks
- Create: isolation test suite
- Create: secret boundary policy docs

- [ ] Enforce project-scoped secret conventions.
- [ ] Block shared/global secret mount patterns.
- [ ] Enforce startup hard gates (OC + MCP + skills + mount integrity).
- [ ] Implement cross-project path/env/cache leakage tests.
- [ ] Add per-runtime evidence artifact output.

## Task 4: Backup, Restore, and Certification

**Files:**
- Create: backup runbook template
- Create: restore validation tooling
- Create: certification report format

- [ ] Define backup manifest and integrity verification flow.
- [ ] Implement generic restore validation runner.
- [ ] Validate post-restore gates (OC/MCP/skills/mount).
- [ ] Run recovery drills for `FIN`, `Marker`, `LLM Wiki`, `JSON`, `Loto`, `Games`.
- [ ] Track blockers with owner and due date until certified.

## Task 5: Provision and Validate P1..P6

**Files:**
- Create: onboarding matrix
- Create: per-project runtime profiles
- Create: provisioning evidence artifacts

- [ ] Build onboarding matrix for all six projects.
- [ ] Provision six sandbox runtimes from the standardized template.
- [ ] Configure project-local secrets and runtime parameters.
- [ ] Run readiness and isolation checks for each runtime.
- [ ] Execute one smoke OC workflow in each runtime.

## Task 6: CI/CD and Governance Controls

**Files:**
- Create: GitHub Actions workflows for core checks
- Create: rollout/rollback policy documentation
- Create: release notes template

- [ ] Add lint/static checks and sample sandbox integration checks.
- [ ] Gate releases on core health checks.
- [ ] Define staged rollout policy (canary -> subset -> all).
- [ ] Define rollback trigger thresholds and hotfix policy.

## Task 7: 30-Day Readiness and Final Sign-Off

**Files:**
- Create: KPI report template/dashboard source
- Create: final acceptance checklist

- [ ] Track provisioning duration, leakage incidents, startup/switch latency.
- [ ] Publish weekly operations summaries.
- [ ] Validate three success outcomes (<30 min setup, zero leakage, fast switching).
- [ ] Run `P7` dry run (or real onboarding) to prove no redesign required.
- [ ] Complete final operational sign-off.

## Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
