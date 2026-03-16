from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.config import paths

SCOPE_LABEL = "m5-scope"
EXCEPTION_LABEL = "m5-expansion-exception"


class ScopeAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class PullRequestRef:
    number: int
    title: str
    url: str
    merged_at: str


@dataclass(frozen=True)
class ScopeAuditResult:
    repo: str
    since: str
    generated_at: str
    total_merged_prs: int
    exception_merges_count: int
    missing_scope_label_merges_count: int
    violations_count: int
    exception_prs: Tuple[PullRequestRef, ...]
    missing_scope_label_prs: Tuple[PullRequestRef, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "repo": self.repo,
            "since": self.since,
            "generated_at": self.generated_at,
            "total_merged_prs": self.total_merged_prs,
            "exception_merges_count": self.exception_merges_count,
            "missing_scope_label_merges_count": self.missing_scope_label_merges_count,
            "violations_count": self.violations_count,
            "exception_prs": [asdict(pr) for pr in self.exception_prs],
            "missing_scope_label_prs": [
                asdict(pr) for pr in self.missing_scope_label_prs
            ],
        }


def _validate_since(value: str) -> str:
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError as e:
        raise ScopeAuditError(
            f"Invalid --since date '{value}'. Expected YYYY-MM-DD."
        ) from e
    return str(value)


def infer_repo_from_origin() -> str:
    env_repo = str(os.environ.get("GITHUB_REPOSITORY", "")).strip()
    if env_repo:
        return env_repo

    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise ScopeAuditError(
            "git not found while resolving repository from origin remote."
        ) from e

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise ScopeAuditError(
            "Could not resolve repository from git origin remote. "
            "Use --repo OWNER/REPO. "
            f"Details: {msg}"
        )

    remote = (proc.stdout or "").strip()
    cleaned = remote
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.startswith("git@github.com:"):
        cleaned = cleaned.split(":", 1)[1]
    elif "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/", 1)[1]

    parts = [p for p in cleaned.split("/") if p]
    if len(parts) < 2:
        raise ScopeAuditError(
            "Could not parse OWNER/REPO from origin remote. Use --repo OWNER/REPO. "
            f"Remote: {remote}"
        )

    owner, repo = parts[-2], parts[-1]
    return f"{owner}/{repo}"


def _run_gh_json(command: Sequence[str]) -> Any:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise ScopeAuditError(
            "gh CLI not found. Install/authenticate gh before running scope audit."
        ) from e

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise ScopeAuditError(f"gh command failed: {' '.join(command)}\n{msg}")

    txt = (proc.stdout or "").strip()
    if not txt:
        return []
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise ScopeAuditError(
            f"gh returned non-JSON output for command: {' '.join(command)}"
        ) from e


def _labels(record: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in list(record.get("labels") or []):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name:
                out.add(name)
    return out


def _as_ref(record: Dict[str, Any]) -> PullRequestRef:
    return PullRequestRef(
        number=int(record.get("number", 0)),
        title=str(record.get("title", "")),
        url=str(record.get("url", "")),
        merged_at=str(record.get("mergedAt", "")),
    )


def list_merged_prs_since(*, repo: str, since: str) -> List[Dict[str, Any]]:
    cmd = [
        "gh",
        "pr",
        "list",
        "-R",
        str(repo),
        "--state",
        "merged",
        "--limit",
        "500",
        "--search",
        f"merged:>={since}",
        "--json",
        "number,title,url,mergedAt,labels",
    ]
    records = _run_gh_json(cmd)
    if not isinstance(records, list):
        raise ScopeAuditError("Unexpected gh response type for merged PR list.")
    return [r for r in records if isinstance(r, dict)]


def compute_scope_audit(
    *, repo: str, since: str, records: Iterable[Dict[str, Any]]
) -> ScopeAuditResult:
    merged: List[Dict[str, Any]] = list(records)
    exception_refs: List[PullRequestRef] = []
    missing_refs: List[PullRequestRef] = []

    for rec in merged:
        names = _labels(rec)
        has_scope = SCOPE_LABEL in names
        has_exception = EXCEPTION_LABEL in names
        pr_ref = _as_ref(rec)
        if has_exception:
            exception_refs.append(pr_ref)
        if (not has_scope) and (not has_exception):
            missing_refs.append(pr_ref)

    exception_refs.sort(key=lambda x: (x.merged_at, x.number))
    missing_refs.sort(key=lambda x: (x.merged_at, x.number))

    return ScopeAuditResult(
        repo=str(repo),
        since=_validate_since(str(since)),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_merged_prs=len(merged),
        exception_merges_count=len(exception_refs),
        missing_scope_label_merges_count=len(missing_refs),
        violations_count=len(missing_refs),
        exception_prs=tuple(exception_refs),
        missing_scope_label_prs=tuple(missing_refs),
    )


def run_scope_audit(*, repo: Optional[str], since: str) -> ScopeAuditResult:
    resolved_repo = (
        str(repo).strip()
        if repo is not None and str(repo).strip()
        else infer_repo_from_origin()
    )
    since_norm = _validate_since(str(since))
    merged = list_merged_prs_since(repo=resolved_repo, since=since_norm)
    return compute_scope_audit(repo=resolved_repo, since=since_norm, records=merged)


def render_scope_audit_markdown(result: ScopeAuditResult) -> str:
    status = "PASS" if result.violations_count == 0 else "FAIL"
    lines: List[str] = []
    lines.append("# Follow-up ML Weekly Scope Audit")
    lines.append("")
    lines.append(f"- Generated at: `{result.generated_at}`")
    lines.append(f"- Repository: `{result.repo}`")
    lines.append(f"- Audit window start: `{result.since}`")
    lines.append(f"- Total merged PRs inspected: `{result.total_merged_prs}`")
    lines.append(
        f"- Exception merges (`{EXCEPTION_LABEL}`): `{result.exception_merges_count}`"
    )
    lines.append(
        "- Merged PRs missing both labels "
        f"(`{SCOPE_LABEL}`, `{EXCEPTION_LABEL}`): `{result.missing_scope_label_merges_count}`"
    )
    lines.append(f"- Violations: `{result.violations_count}`")
    lines.append(f"- Result: `{status}`")
    lines.append("")
    lines.append("## Query references")
    lines.append("")
    lines.append(
        "- `gh pr list --state merged --label m5-expansion-exception "
        f'--search "merged:>={result.since}"`'
    )
    lines.append(
        "- `gh pr list --state merged --search "
        f'"merged:>={result.since} -label:m5-scope -label:m5-expansion-exception"`'
    )
    lines.append("")

    lines.append("## Exception merges")
    lines.append("")
    lines.append("| PR | Merged at | Title |")
    lines.append("|:--|:--|:--|")
    if result.exception_prs:
        for pr in result.exception_prs:
            lines.append(
                f"| #{pr.number} | {pr.merged_at or '-'} | [{pr.title}]({pr.url}) |"
            )
    else:
        lines.append("| - | - | none |")
    lines.append("")

    lines.append("## Missing-scope-label merges")
    lines.append("")
    lines.append("| PR | Merged at | Title |")
    lines.append("|:--|:--|:--|")
    if result.missing_scope_label_prs:
        for pr in result.missing_scope_label_prs:
            lines.append(
                f"| #{pr.number} | {pr.merged_at or '-'} | [{pr.title}]({pr.url}) |"
            )
    else:
        lines.append("| - | - | none |")
    lines.append("")
    return "\n".join(lines)


def default_scope_audit_report_path(*, since: str) -> Path:
    since_slug = _validate_since(str(since)).replace("-", "")
    return paths.OUT_I_CALC_FOLLOWUP_ML_DIR / "reports" / f"scope_audit_{since_slug}.md"


def write_scope_audit_report(
    result: ScopeAuditResult, *, out_path: Optional[Path] = None
) -> Path:
    p = (
        out_path
        if out_path is not None
        else default_scope_audit_report_path(since=result.since)
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_scope_audit_markdown(result), encoding="utf-8")
    return p
