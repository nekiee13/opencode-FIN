#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-nekiee13/opencode-agent-core}"
PLAN_PATH="docs/superpowers/plans/2026-04-15-oc-multi-project-sandbox-rollout.md"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf "Missing required command: %s\n" "$1" >&2
    exit 1
  fi
}

require_cmd gh

if ! gh auth status >/dev/null 2>&1; then
  printf "GitHub CLI is not authenticated. Run: gh auth login\n" >&2
  exit 1
fi

ensure_label() {
  local name="$1"
  local color="$2"
  local desc="$3"
  gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" --force >/dev/null
}

ensure_milestone() {
  local title="$1"
  local desc="$2"
  local existing=""
  while IFS= read -r line; do
    existing="$line"
    break
  done < <(gh api "repos/$REPO/milestones?state=all&per_page=100" --jq ".[] | select(.title==\"$title\") | .number")

  if [[ -z "$existing" ]]; then
    gh api --method POST "repos/$REPO/milestones" -f title="$title" -f description="$desc" >/dev/null
  fi
}

issue_number_by_title() {
  local title="$1"
  local existing=""
  while IFS= read -r line; do
    existing="$line"
    break
  done < <(gh issue list --repo "$REPO" --state all --limit 300 --search "\"$title\" in:title" --json number,title --jq ".[] | select(.title==\"$title\") | .number")
  printf "%s" "$existing"
}

create_or_get_issue() {
  local key="$1"
  local title="$2"
  local milestone="$3"
  local labels_csv="$4"
  local depends="$5"
  local blocks="$6"
  local summary="$7"

  local existing
  existing="$(issue_number_by_title "$title")"
  if [[ -n "$existing" ]]; then
    printf "%s\n" "$existing"
    return 0
  fi

  local body
  body=$(cat <<EOF
## Summary
$summary

## Tasks
- [ ] Implement scope for this issue according to \
  \
  \`$PLAN_PATH\`
- [ ] Add/refresh verification checks relevant to this scope
- [ ] Update operational documentation if behavior changes

## Acceptance Criteria
- [ ] Scope implemented and validated
- [ ] Evidence/artifacts attached in the issue
- [ ] No cross-project isolation regressions introduced

## Dependencies (by key)
- Depends on: ${depends:-None}
- Blocks: ${blocks:-None}
EOF
)

  local -a label_args=()
  IFS=',' read -r -a labels <<<"$labels_csv"
  for label in "${labels[@]}"; do
    label_args+=(--label "$label")
  done

  local out
  out=$(gh issue create --repo "$REPO" --title "$title" --body "$body" --milestone "$milestone" "${label_args[@]}")
  printf "%s\n" "${out##*/}"
}

printf "Bootstrapping labels in %s\n" "$REPO"

while IFS=$'\t' read -r name color desc; do
  [[ -z "${name:-}" ]] && continue
  ensure_label "$name" "$color" "$desc"
done <<'EOF'
epic:1	1f6feb	Core productization
epic:2	5319e7	Template and lifecycle automation
epic:3	d73a4a	Isolation and security controls
epic:4	0e8a16	Backup and recovery
epic:5	fbca04	P1..P6 rollout
epic:6	0052cc	CI/CD and governance
epic:7	c2e0c6	Operational readiness
type:setup	bfdadc	Initial repository setup
type:migration	cfd3d7	Migration work
type:quality	0366d6	Quality controls
type:design	f9d0c4	Design and contracts
type:automation	a2eeef	Automation scripts
type:scalability	7057ff	Scalability and expansion
type:security	d93f0b	Security scope
type:test	e4e669	Testing scope
type:reliability	006b75	Reliability scope
type:ops	fef2c0	Operations scope
type:recovery	b60205	Recovery scope
type:drill	ededed	Drill exercises
type:planning	c5def5	Planning and inventory
type:provisioning	0b7fab	Provisioning scope
type:validation	fbca04	Validation scope
type:ci	1d76db	CI pipeline scope
type:governance	5319e7	Governance scope
type:metrics	9be9a8	KPI and metrics scope
type:acceptance	7057ff	Final acceptance scope
priority:high	b60205	High priority
priority:medium	fbca04	Medium priority
EOF

printf "Bootstrapping milestones in %s\n" "$REPO"

ensure_milestone "M1 Core Productization" "Core repository productization and baseline checks"
ensure_milestone "M2 Template + Isolation Controls" "Template lifecycle automation and security controls"
ensure_milestone "M3 Recovery + P1..P6 Rollout" "Recovery standardization and six project rollout"
ensure_milestone "M4 Governance + 30-Day Acceptance" "Governance, KPI, and final operational sign-off"

declare -A ISSUE_NUM=()

printf "Creating or reusing issues in %s\n" "$REPO"

while IFS=$'\t' read -r key title milestone labels depends blocks summary; do
  [[ -z "${key:-}" ]] && continue
  num="$(create_or_get_issue "$key" "$title" "$milestone" "$labels" "$depends" "$blocks" "$summary")"
  ISSUE_NUM["$key"]="$num"
  printf "  %s -> #%s\n" "$key" "$num"
done <<'EOF'
E1.1	E1.1 Create opencode-agent-core repository skeleton	M1 Core Productization	epic:1,type:setup,priority:high	None	E1.2	Create baseline core repository structure and governance docs.
E1.2	E1.2 Extract OC stack from FIN into opencode-agent-core	M1 Core Productization	epic:1,type:migration,priority:high	E1.1	E1.3,E2.1	Port OC runtime, MCP, Superpowers, and OAC templates into a reusable core.
E1.3	E1.3 Add core stack health-check suite	M1 Core Productization	epic:1,type:quality,priority:high	E1.2	E2.2,E3.3,E6.1	Implement gate checks for OC runtime, MCP connectivity, and skill visibility.
E2.1	E2.1 Define standard sandbox contract	M2 Template + Isolation Controls	epic:2,type:design,priority:high	E1.2	E2.2,E3.1,E4.1,E5.1	Define required folders, env schema, and mount policy for all runtimes.
E2.2	E2.2 Implement create-sandbox automation	M2 Template + Isolation Controls	epic:2,type:automation,priority:high	E2.1,E1.3	E2.3,E2.4,E3.2,E3.3,E5.2,E6.1	Automate sandbox provisioning from template with dry-run and metadata.
E2.3	E2.3 Implement update-sandbox and drift detection	M2 Template + Isolation Controls	epic:2,type:automation,priority:high	E2.2	E6.2	Automate safe upgrades with snapshots, drift states, and rollback path.
E2.4	E2.4 Implement add-project workflow for P7+	M2 Template + Isolation Controls	epic:2,type:scalability,priority:high	E2.2,E3.3	None	Enable onboarding of new projects without architecture changes.
E3.1	E3.1 Enforce per-project secrets boundary	M2 Template + Isolation Controls	epic:3,type:security,priority:high	E2.1	E3.2	Enforce secret scope per runtime and block shared secret mounts.
E3.2	E3.2 Implement cross-project isolation tests	M2 Template + Isolation Controls	epic:3,type:test,priority:high	E3.1,E2.2	None	Prove file/env/cache isolation across all runtime instances.
E3.3	E3.3 Implement runtime startup hard gates	M2 Template + Isolation Controls	epic:3,type:reliability,priority:high	E1.3,E2.2	E2.4,E4.2,E5.2	Block runtime readiness unless all required gates pass.
E4.1	E4.1 Create per-project backup runbook template	M3 Recovery + P1..P6 Rollout	epic:4,type:ops,priority:medium	E2.1	E4.2	Standardize backup manifests, integrity checks, and restore procedures.
E4.2	E4.2 Build automated restore validation for generic runtime	M3 Recovery + P1..P6 Rollout	epic:4,type:recovery,priority:high	E4.1,E3.3	E4.3	Validate OC/MCP/skills/mount integrity after restore.
E4.3	E4.3 Execute recovery drills for P1..P6	M3 Recovery + P1..P6 Rollout	epic:4,type:drill,priority:high	E4.2	E7.2	Run and certify restore drills for FIN, Marker, LLM Wiki, JSON, Loto, Games.
E5.1	E5.1 Build onboarding matrix for P1..P6	M3 Recovery + P1..P6 Rollout	epic:5,type:planning,priority:high	E2.1	E5.2	Capture runtime profiles and onboarding metadata for all six projects.
E5.2	E5.2 Provision sandbox instances for P1..P6	M3 Recovery + P1..P6 Rollout	epic:5,type:provisioning,priority:high	E5.1,E2.2,E3.3	E5.3,E7.1	Provision and validate six isolated project runtime instances.
E5.3	E5.3 Run smoke workflow in each project sandbox	M3 Recovery + P1..P6 Rollout	epic:5,type:validation,priority:medium	E5.2	E7.2	Run one low-risk OC workflow per runtime and capture evidence.
E6.1	E6.1 Add CI pipeline for opencode-agent-core	M4 Governance + 30-Day Acceptance	epic:6,type:ci,priority:medium	E1.3,E2.2	E6.2	Protect core quality with automated checks and release gating.
E6.2	E6.2 Define governance, rollout, and rollback policy	M4 Governance + 30-Day Acceptance	epic:6,type:governance,priority:medium	E2.3,E6.1	E7.2	Define staged rollout, rollback thresholds, and hotfix policy.
E7.1	E7.1 Implement KPI instrumentation for 30-day goals	M4 Governance + 30-Day Acceptance	epic:7,type:metrics,priority:medium	E5.2	E7.2	Measure provisioning time, leakage incidents, and runtime switch latency.
E7.2	E7.2 Final acceptance review and operational sign-off	M4 Governance + 30-Day Acceptance	epic:7,type:acceptance,priority:high	E4.3,E5.3,E6.2,E7.1	None	Complete final readiness audit, P7+ proof, and sign-off package.
EOF

printf "\nIssue map (key -> #number):\n"
for key in E1.1 E1.2 E1.3 E2.1 E2.2 E2.3 E2.4 E3.1 E3.2 E3.3 E4.1 E4.2 E4.3 E5.1 E5.2 E5.3 E6.1 E6.2 E7.1 E7.2; do
  printf "- %s -> #%s\n" "$key" "${ISSUE_NUM[$key]}"
done

printf "\nDone. Next: manually add issue links in dependency sections if needed.\n"
