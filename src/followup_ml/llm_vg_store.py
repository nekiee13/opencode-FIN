from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.config import paths


LLM_VG_SCHEMA_VERSION = "llm-vg-v1"
MARKERS_SCHEMA_VERSION = "markers-v1"
DEFAULT_POLICY_NAME = "value_assign_v1"

LLM_MODEL_ORDER_DEFAULT: Sequence[str] = (
    "OAI",
    "GROK",
    "GEMINI",
    "CLAUDE",
    "GLM",
    "KIMI",
    "QWEN",
    "LECHAT",
    "MINIMAX",
)

TICKER_ORDER_DEFAULT: Sequence[str] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")

MARKER_CLOSE_YAHOO = "close_yahoo_finance"
MARKER_CLOSE_INVESTING = "close_investing_com"
MARKER_CLOSE_ANCHOR = "close_anchor_mark"
MARKER_CLOSE_REAL_TPLUS3 = "close_real_tplus3"

MARKER_LABEL_MAP: Dict[str, str] = {
    "close yahoo finance": MARKER_CLOSE_YAHOO,
    "close investing.com": MARKER_CLOSE_INVESTING,
    "close anchor mark": MARKER_CLOSE_ANCHOR,
    "close oraclum": MARKER_CLOSE_ANCHOR,
    "+3-day close real": MARKER_CLOSE_REAL_TPLUS3,
    "+3 day close real": MARKER_CLOSE_REAL_TPLUS3,
    "rd": "RD",
    "85220": "85220",
    "mich": "MICH",
}


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        txt = str(value).strip()
        if txt == "" or txt.lower() in {"nan", "none", "null", "-"}:
            return None
        txt = txt.replace(",", "")
        return float(txt)
    except Exception:
        return None


def _to_date_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    txt = str(value).strip()
    if txt == "":
        return None
    candidates = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    )
    for fmt in candidates:
        try:
            return datetime.strptime(txt, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def _normalized_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _clean_label(text: str) -> str:
    t = str(text).replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    t = re.sub(r"\*\*", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return _normalized_whitespace(t)


def _label_key(text: str) -> str:
    t = _clean_label(text).lower()
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"[^a-z0-9+\-\. ]+", " ", t)
    return _normalized_whitespace(t)


def _strip_alignment_row(cells: Sequence[str]) -> bool:
    if not cells:
        return True
    if all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells):
        return True
    return False


def _parse_markdown_table(markdown_text: str) -> Tuple[List[str], List[List[str]]]:
    rows: List[List[str]] = []
    for line in str(markdown_text).splitlines():
        ln = line.strip()
        if not ln.startswith("|"):
            continue
        parts = [p.strip() for p in ln.strip("|").split("|")]
        if parts:
            rows.append(parts)

    if not rows:
        raise ValueError("No markdown table rows detected")

    header_idx = 0
    for i, row in enumerate(rows):
        if row and _label_key(row[0]) in {"ticker", "model"}:
            header_idx = i
            break

    header = rows[header_idx]
    body = rows[header_idx + 1 :]
    body = [r for r in body if not _strip_alignment_row(r)]
    return header, body


def _extract_last_numeric(text: str) -> Optional[float]:
    if text is None:
        return None
    t = str(text)
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    t = t.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    t = re.sub(r"<[^>]+>", "", t)

    bold_matches = re.findall(r"\*\*(.*?)\*\*", t, flags=re.DOTALL)
    candidate = bold_matches[-1] if bold_matches else ""
    candidate = candidate.strip()

    number_re = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

    search_zones: List[str] = []
    if candidate:
        search_zones.append(candidate)

    lines = [x.strip() for x in t.splitlines() if x.strip() and x.strip() != "---"]
    if lines:
        search_zones.append(lines[-1])

    search_zones.append(t)
    for zone in search_zones:
        zone_norm = zone.replace(",", "")
        matches = re.findall(number_re, zone_norm)
        if matches:
            raw = matches[-1]
            try:
                return float(raw)
            except Exception:
                continue
    return None


def _load_llm_defaults() -> Tuple[int, bool, float]:
    tail = 4
    bootstrap_enabled = True
    bootstrap_score = 99.0
    try:
        import Constants as C  # type: ignore

        tail = int(getattr(C, "LLM_VBG_MEMORY_TAIL", tail))
        bootstrap_enabled = bool(
            getattr(C, "LLM_VBG_BOOTSTRAP_ENABLED", bootstrap_enabled)
        )
        bootstrap_score = float(getattr(C, "LLM_VBG_BOOTSTRAP_SCORE", bootstrap_score))
    except Exception:
        pass

    if tail <= 0:
        tail = 4
    return tail, bootstrap_enabled, bootstrap_score


def resolve_llm_vg_db_path(db_path: Optional[Path] = None) -> Path:
    env = os.getenv("FIN_LLM_VG_DB", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if db_path is not None:
        return Path(db_path).expanduser().resolve()
    try:
        import Constants as C  # type: ignore

        cfg = str(getattr(C, "LLM_VG_DB_FILE", "")).strip()
        if cfg:
            return Path(cfg).expanduser().resolve()
    except Exception:
        pass
    return paths.OUT_I_CALC_LLM_VG_DB_PATH.resolve()


def resolve_markers_db_path(db_path: Optional[Path] = None) -> Path:
    env = os.getenv("FIN_MARKERS_DB", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if db_path is not None:
        return Path(db_path).expanduser().resolve()
    try:
        import Constants as C  # type: ignore

        cfg = str(getattr(C, "MARKERS_DB_FILE", "")).strip()
        if cfg:
            return Path(cfg).expanduser().resolve()
    except Exception:
        pass
    return paths.OUT_I_CALC_MARKERS_DB_PATH.resolve()


def connect_llm_vg_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    p = resolve_llm_vg_db_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_markers_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    p = resolve_markers_db_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_llm_vg_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rounds (
            forecast_date TEXT PRIMARY KEY,
            round_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(length(forecast_date) = 10)
        );

        CREATE TABLE IF NOT EXISTS model_aliases (
            alias_pattern TEXT PRIMARY KEY,
            canonical_model TEXT NOT NULL,
            match_type TEXT NOT NULL,
            priority INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(match_type IN ('contains', 'prefix', 'exact', 'regex')),
            CHECK(is_active IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS llm_predictions (
            forecast_date TEXT NOT NULL,
            round_id TEXT,
            ticker TEXT NOT NULL,
            raw_model_label TEXT NOT NULL,
            canonical_model TEXT NOT NULL,
            predicted_value REAL,
            alias_resolved INTEGER NOT NULL,
            alias_pattern TEXT,
            source_table_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (forecast_date, ticker, canonical_model),
            FOREIGN KEY (forecast_date) REFERENCES rounds(forecast_date) ON DELETE CASCADE,
            CHECK(alias_resolved IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS transform_policies (
            policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_name TEXT NOT NULL UNIQUE,
            mode TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(mode IN ('step_floor', 'piecewise_linear')),
            CHECK(is_active IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS transform_points (
            policy_id INTEGER NOT NULL,
            point_order INTEGER NOT NULL,
            x_value REAL NOT NULL,
            y_value REAL NOT NULL,
            PRIMARY KEY (policy_id, point_order),
            FOREIGN KEY (policy_id) REFERENCES transform_policies(policy_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS materialization_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            forecast_date TEXT NOT NULL,
            policy_id INTEGER NOT NULL,
            policy_name TEXT NOT NULL,
            marker_name TEXT NOT NULL,
            memory_tail INTEGER NOT NULL,
            bootstrap_enabled INTEGER NOT NULL,
            bootstrap_score REAL NOT NULL,
            cells_total INTEGER NOT NULL,
            cells_green_real INTEGER NOT NULL,
            cells_green_bootstrap INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            CHECK(bootstrap_enabled IN (0, 1)),
            FOREIGN KEY (policy_id) REFERENCES transform_policies(policy_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_round_id_unique
            ON rounds(round_id)
            WHERE round_id IS NOT NULL AND round_id <> '';

        CREATE INDEX IF NOT EXISTS idx_llm_predictions_date
            ON llm_predictions(forecast_date);
        CREATE INDEX IF NOT EXISTS idx_llm_predictions_model_ticker_date
            ON llm_predictions(canonical_model, ticker, forecast_date);
        CREATE INDEX IF NOT EXISTS idx_model_aliases_active_priority
            ON model_aliases(is_active, priority);
        """
    )
    now = _now_ts()
    conn.execute(
        """
        INSERT INTO schema_meta(meta_key, meta_value, updated_at)
        VALUES('schema_version', ?, ?)
        ON CONFLICT(meta_key) DO UPDATE SET
            meta_value=excluded.meta_value,
            updated_at=excluded.updated_at
        """,
        (LLM_VG_SCHEMA_VERSION, now),
    )
    conn.commit()


def initialize_markers_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS marker_values (
            forecast_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            marker_name TEXT NOT NULL,
            marker_value REAL,
            source_label TEXT,
            source_table_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (forecast_date, ticker, marker_name),
            CHECK(length(forecast_date) = 10)
        );

        CREATE INDEX IF NOT EXISTS idx_marker_values_date_name
            ON marker_values(forecast_date, marker_name);
        """
    )
    now = _now_ts()
    conn.execute(
        """
        INSERT INTO schema_meta(meta_key, meta_value, updated_at)
        VALUES('schema_version', ?, ?)
        ON CONFLICT(meta_key) DO UPDATE SET
            meta_value=excluded.meta_value,
            updated_at=excluded.updated_at
        """,
        (MARKERS_SCHEMA_VERSION, now),
    )
    conn.commit()


def _default_alias_rules() -> List[Tuple[str, str, str, int]]:
    return [
        ("openai", "OAI", "contains", 10),
        ("oai", "OAI", "contains", 11),
        ("o ", "OAI", "prefix", 12),
        ("^o[0-9]", "OAI", "regex", 13),
        ("grok", "GROK", "contains", 20),
        ("gemini", "GEMINI", "contains", 30),
        ("claude", "CLAUDE", "contains", 40),
        ("glm", "GLM", "contains", 50),
        ("kimi", "KIMI", "contains", 60),
        ("qwen", "QWEN", "contains", 70),
        ("lechat", "LECHAT", "contains", 80),
        ("mini max", "MINIMAX", "contains", 90),
        ("minimax", "MINIMAX", "contains", 91),
    ]


def seed_default_aliases(conn: sqlite3.Connection) -> int:
    now = _now_ts()
    rows = _default_alias_rules()
    conn.executemany(
        """
        INSERT INTO model_aliases(
            alias_pattern,
            canonical_model,
            match_type,
            priority,
            is_active,
            created_at,
            updated_at
        ) VALUES(?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(alias_pattern) DO UPDATE SET
            canonical_model=excluded.canonical_model,
            match_type=excluded.match_type,
            priority=excluded.priority,
            updated_at=excluded.updated_at
        """,
        [(p, c, m, int(pr), now, now) for p, c, m, pr in rows],
    )
    conn.commit()
    return len(rows)


def list_alias_rules(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT alias_pattern, canonical_model, match_type, priority
        FROM model_aliases
        WHERE is_active = 1
        ORDER BY priority ASC, LENGTH(alias_pattern) DESC
        """
    ).fetchall()


def canonicalize_model_label(
    raw_label: str,
    alias_rules: Sequence[sqlite3.Row],
) -> Tuple[str, int, str]:
    original = _normalized_whitespace(str(raw_label))
    raw_lower = original.lower()
    for rule in alias_rules:
        pattern = str(rule["alias_pattern"])
        canonical = str(rule["canonical_model"])
        match_type = str(rule["match_type"])
        if match_type == "exact" and raw_lower == pattern.lower():
            return canonical, 1, pattern
        if match_type == "prefix" and raw_lower.startswith(pattern.lower()):
            return canonical, 1, pattern
        if match_type == "contains" and pattern.lower() in raw_lower:
            return canonical, 1, pattern
        if match_type == "regex":
            try:
                if re.search(pattern, raw_lower):
                    return canonical, 1, pattern
            except re.error:
                continue

    fallback = re.sub(r"[^A-Za-z0-9]+", "_", original).strip("_").upper()
    if not fallback:
        fallback = "UNKNOWN_MODEL"
    return fallback, 0, ""


def _default_points() -> List[Tuple[float, float]]:
    return [
        (0.0, 0.0),
        (50.0, 50.0),
        (70.0, 70.0),
        (80.0, 80.0),
        (90.0, 90.0),
        (95.0, 95.0),
        (97.0, 97.0),
        (98.0, 98.0),
        (99.0, 99.0),
        (99.5, 99.5),
        (99.75, 99.75),
        (99.9, 99.9),
        (99.99, 100.0),
    ]


def _load_mapping_points_from_csv() -> List[Tuple[float, float]]:
    p = paths.FOLLOWUP_ML_VALUE_ASSIGN_PATH.resolve()
    if not p.exists():
        return _default_points()

    pts: List[Tuple[float, float]] = []
    try:
        with p.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                x = _to_float_or_none(row.get("value"))
                y = _to_float_or_none(row.get("assign"))
                if x is None or y is None:
                    continue
                pts.append((x, y))
    except Exception:
        return _default_points()

    if not pts:
        return _default_points()

    dedup: Dict[float, float] = {}
    for x, y in pts:
        dedup[float(x)] = float(y)
    return sorted(dedup.items(), key=lambda t: t[0])


def upsert_transform_policy(
    conn: sqlite3.Connection,
    *,
    policy_name: str,
    mode: str,
    points: Sequence[Tuple[float, float]],
    set_active: bool = True,
) -> int:
    if mode not in {"step_floor", "piecewise_linear"}:
        raise ValueError(f"Unsupported transform mode: {mode}")
    if not points:
        raise ValueError("Transform points cannot be empty")

    clean = sorted((float(x), float(y)) for x, y in points)
    now = _now_ts()
    conn.execute(
        """
        INSERT INTO transform_policies(policy_name, mode, is_active, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(policy_name) DO UPDATE SET
            mode=excluded.mode,
            updated_at=excluded.updated_at
        """,
        (str(policy_name), str(mode), 1 if set_active else 0, now, now),
    )
    row = conn.execute(
        "SELECT policy_id FROM transform_policies WHERE policy_name = ?",
        (str(policy_name),),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Failed to resolve transform policy id: {policy_name}")
    policy_id = int(row["policy_id"])

    conn.execute("DELETE FROM transform_points WHERE policy_id = ?", (policy_id,))
    conn.executemany(
        """
        INSERT INTO transform_points(policy_id, point_order, x_value, y_value)
        VALUES(?, ?, ?, ?)
        """,
        [(policy_id, i, x, y) for i, (x, y) in enumerate(clean)],
    )
    if set_active:
        conn.execute(
            "UPDATE transform_policies SET is_active = CASE WHEN policy_id = ? THEN 1 ELSE 0 END",
            (policy_id,),
        )
    conn.commit()
    return policy_id


def ensure_default_transform_policy(conn: sqlite3.Connection) -> int:
    return upsert_transform_policy(
        conn,
        policy_name=DEFAULT_POLICY_NAME,
        mode="step_floor",
        points=_load_mapping_points_from_csv(),
        set_active=True,
    )


def _get_policy(
    conn: sqlite3.Connection,
    policy_name: Optional[str],
) -> Tuple[int, str, str, List[Tuple[float, float]]]:
    row: Optional[sqlite3.Row]
    if policy_name:
        row = conn.execute(
            "SELECT policy_id, policy_name, mode FROM transform_policies WHERE policy_name = ?",
            (str(policy_name),),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT policy_id, policy_name, mode FROM transform_policies WHERE is_active = 1 ORDER BY policy_id DESC LIMIT 1"
        ).fetchone()

    if row is None:
        ensure_default_transform_policy(conn)
        row = conn.execute(
            "SELECT policy_id, policy_name, mode FROM transform_policies WHERE is_active = 1 ORDER BY policy_id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("No transform policy available")

    policy_id = int(row["policy_id"])
    point_rows = conn.execute(
        "SELECT x_value, y_value FROM transform_points WHERE policy_id = ? ORDER BY point_order",
        (policy_id,),
    ).fetchall()
    points = [(float(r["x_value"]), float(r["y_value"])) for r in point_rows]
    if not points:
        raise RuntimeError("Transform policy has no points")
    return policy_id, str(row["policy_name"]), str(row["mode"]), points


def _transform_accuracy(
    accuracy_pct: Optional[float], mode: str, points: Sequence[Tuple[float, float]]
) -> Optional[float]:
    if accuracy_pct is None:
        return None
    x = float(accuracy_pct)
    if mode == "step_floor":
        best = points[0][1]
        for px, py in points:
            if x >= px:
                best = py
            else:
                break
        return float(best)

    if mode == "piecewise_linear":
        if x <= points[0][0]:
            return float(points[0][1])
        if x >= points[-1][0]:
            return float(points[-1][1])
        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            if x <= x1:
                if x1 == x0:
                    return float(y1)
                ratio = (x - x0) / (x1 - x0)
                return float(y0 + ratio * (y1 - y0))
        return float(points[-1][1])

    raise ValueError(f"Unsupported transform mode: {mode}")


def parse_llm_model_table(markdown_text: str) -> Dict[str, Any]:
    header, body = _parse_markdown_table(markdown_text)
    tickers = [str(_clean_label(h)).upper() for h in header[1:] if _clean_label(h)]
    tickers = [t for t in tickers if t in set(TICKER_ORDER_DEFAULT)]
    if not tickers:
        raise ValueError("No ticker headers detected in model table")

    ignore_rows = {
        "ticker",
        "close yahoo finance",
        "close investing.com",
        "close anchor mark",
        "close oraclum",
        "+3-day close real",
        "+3 day close real",
        "rd",
        "85220",
        "mich",
    }

    models: List[Dict[str, Any]] = []
    for row in body:
        if not row:
            continue
        label_raw = _clean_label(row[0])
        key = _label_key(label_raw)
        if key in ignore_rows or key == "":
            continue

        vals: Dict[str, Optional[float]] = {}
        non_null = 0
        for i, t in enumerate(tickers, start=1):
            cell = row[i] if i < len(row) else ""
            num = _extract_last_numeric(cell)
            vals[t] = num
            if num is not None:
                non_null += 1
        if non_null == 0:
            continue

        models.append(
            {
                "raw_model_label": label_raw,
                "values": vals,
            }
        )

    return {
        "tickers": tickers,
        "models": models,
    }


def parse_markers_table(markdown_text: str) -> Dict[str, Any]:
    header, body = _parse_markdown_table(markdown_text)
    tickers = [str(_clean_label(h)).upper() for h in header[1:] if _clean_label(h)]
    tickers = [t for t in tickers if t in set(TICKER_ORDER_DEFAULT)]
    if not tickers:
        raise ValueError("No ticker headers detected in markers table")

    rows: List[Dict[str, Any]] = []
    for row in body:
        if not row:
            continue
        raw_label = _clean_label(row[0])
        key = _label_key(raw_label)
        marker_name = MARKER_LABEL_MAP.get(key)
        if marker_name is None:
            continue

        vals: Dict[str, Optional[float]] = {}
        non_null = 0
        for i, t in enumerate(tickers, start=1):
            cell = row[i] if i < len(row) else ""
            num = _extract_last_numeric(cell)
            vals[t] = num
            if num is not None:
                non_null += 1
        if non_null == 0:
            continue

        rows.append(
            {
                "source_label": raw_label,
                "marker_name": marker_name,
                "values": vals,
            }
        )

    return {
        "tickers": tickers,
        "markers": rows,
    }


def upsert_round(
    conn: sqlite3.Connection,
    *,
    forecast_date: str,
    round_id: str,
) -> None:
    now = _now_ts()
    conn.execute(
        """
        INSERT INTO rounds(forecast_date, round_id, created_at, updated_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(forecast_date) DO UPDATE SET
            round_id=excluded.round_id,
            updated_at=excluded.updated_at
        """,
        (str(forecast_date), str(round_id), now, now),
    )


def upsert_llm_predictions(
    conn: sqlite3.Connection,
    *,
    forecast_date: str,
    round_id: str,
    source_table_path: str,
    rows: Sequence[Dict[str, Any]],
) -> int:
    now = _now_ts()
    payload: List[Tuple[Any, ...]] = []
    for row in rows:
        payload.append(
            (
                str(forecast_date),
                str(round_id),
                str(row.get("ticker", "")).strip(),
                str(row.get("raw_model_label", "")).strip(),
                str(row.get("canonical_model", "")).strip(),
                _to_float_or_none(row.get("predicted_value")),
                int(row.get("alias_resolved", 0)),
                str(row.get("alias_pattern", "")),
                str(source_table_path),
                now,
                now,
            )
        )

    conn.executemany(
        """
        INSERT INTO llm_predictions(
            forecast_date,
            round_id,
            ticker,
            raw_model_label,
            canonical_model,
            predicted_value,
            alias_resolved,
            alias_pattern,
            source_table_path,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_date, ticker, canonical_model) DO UPDATE SET
            round_id=excluded.round_id,
            raw_model_label=excluded.raw_model_label,
            predicted_value=excluded.predicted_value,
            alias_resolved=excluded.alias_resolved,
            alias_pattern=excluded.alias_pattern,
            source_table_path=excluded.source_table_path,
            updated_at=excluded.updated_at
        """,
        payload,
    )
    return len(payload)


def upsert_marker_values(
    conn: sqlite3.Connection,
    *,
    forecast_date: str,
    source_table_path: str,
    rows: Sequence[Dict[str, Any]],
) -> int:
    now = _now_ts()
    payload: List[Tuple[Any, ...]] = []
    for row in rows:
        payload.append(
            (
                str(forecast_date),
                str(row.get("ticker", "")).strip(),
                str(row.get("marker_name", "")).strip(),
                _to_float_or_none(row.get("marker_value")),
                str(row.get("source_label", "")).strip(),
                str(source_table_path),
                now,
                now,
            )
        )

    conn.executemany(
        """
        INSERT INTO marker_values(
            forecast_date,
            ticker,
            marker_name,
            marker_value,
            source_label,
            source_table_path,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_date, ticker, marker_name) DO UPDATE SET
            marker_value=excluded.marker_value,
            source_label=excluded.source_label,
            source_table_path=excluded.source_table_path,
            updated_at=excluded.updated_at
        """,
        payload,
    )
    return len(payload)


def ingest_llm_model_table_from_markdown(
    *,
    forecast_date: str,
    round_id: str,
    markdown_path: Path,
    llm_db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    date_norm = _to_date_or_none(forecast_date)
    if not date_norm:
        raise ValueError(f"Invalid forecast_date: {forecast_date!r}")
    if not markdown_path.exists():
        raise FileNotFoundError(f"Missing markdown table file: {markdown_path}")

    parsed = parse_llm_model_table(markdown_path.read_text(encoding="utf-8"))

    conn = connect_llm_vg_db(llm_db_path)
    try:
        initialize_llm_vg_db(conn)
        ensure_default_transform_policy(conn)
        seed_default_aliases(conn)
        upsert_round(conn, forecast_date=date_norm, round_id=str(round_id))

        alias_rules = list_alias_rules(conn)
        payload_rows: List[Dict[str, Any]] = []
        unresolved_labels: List[str] = []

        for model_row in parsed["models"]:
            raw_label = str(model_row["raw_model_label"])
            canonical, resolved, alias_pattern = canonicalize_model_label(
                raw_label, alias_rules
            )
            if resolved == 0:
                unresolved_labels.append(raw_label)
            values = model_row["values"]
            for ticker in parsed["tickers"]:
                payload_rows.append(
                    {
                        "ticker": ticker,
                        "raw_model_label": raw_label,
                        "canonical_model": canonical,
                        "predicted_value": values.get(ticker),
                        "alias_resolved": resolved,
                        "alias_pattern": alias_pattern,
                    }
                )

        upserted = upsert_llm_predictions(
            conn,
            forecast_date=date_norm,
            round_id=str(round_id),
            source_table_path=str(markdown_path.resolve()),
            rows=payload_rows,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "forecast_date": date_norm,
        "round_id": str(round_id),
        "tickers": list(parsed["tickers"]),
        "models_total": int(len(parsed["models"])),
        "rows_upserted": int(upserted),
        "unresolved_model_labels": sorted(set(unresolved_labels)),
        "db_path": str(resolve_llm_vg_db_path(llm_db_path)),
    }


def ingest_markers_from_markdown(
    *,
    forecast_date: str,
    markdown_path: Path,
    markers_db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    date_norm = _to_date_or_none(forecast_date)
    if not date_norm:
        raise ValueError(f"Invalid forecast_date: {forecast_date!r}")
    if not markdown_path.exists():
        raise FileNotFoundError(f"Missing markdown table file: {markdown_path}")

    parsed = parse_markers_table(markdown_path.read_text(encoding="utf-8"))

    rows: List[Dict[str, Any]] = []
    for marker_row in parsed["markers"]:
        marker_name = str(marker_row["marker_name"])
        source_label = str(marker_row["source_label"])
        vals = marker_row["values"]
        for ticker in parsed["tickers"]:
            rows.append(
                {
                    "ticker": ticker,
                    "marker_name": marker_name,
                    "marker_value": vals.get(ticker),
                    "source_label": source_label,
                }
            )

    conn = connect_markers_db(markers_db_path)
    try:
        initialize_markers_db(conn)
        upserted = upsert_marker_values(
            conn,
            forecast_date=date_norm,
            source_table_path=str(markdown_path.resolve()),
            rows=rows,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "forecast_date": date_norm,
        "tickers": list(parsed["tickers"]),
        "marker_rows": int(len(parsed["markers"])),
        "rows_upserted": int(upserted),
        "db_path": str(resolve_markers_db_path(markers_db_path)),
    }


def _ordered_labels(
    seen_labels: Iterable[str],
    preferred: Sequence[str],
) -> List[str]:
    seen = {str(x) for x in seen_labels}
    ordered = [x for x in preferred if x in seen]
    extras = sorted(x for x in seen if x not in set(preferred))
    return ordered + extras


def materialize_llm_vbg_for_date(
    forecast_date: str,
    *,
    llm_db_path: Optional[Path] = None,
    markers_db_path: Optional[Path] = None,
    policy_name: Optional[str] = None,
    memory_tail: Optional[int] = None,
    bootstrap_enabled: Optional[bool] = None,
    bootstrap_score: Optional[float] = None,
    marker_name_for_scoring: str = MARKER_CLOSE_REAL_TPLUS3,
) -> Dict[str, Any]:
    date_norm = _to_date_or_none(forecast_date)
    if not date_norm:
        raise ValueError(f"Invalid forecast_date: {forecast_date!r}")

    tail_default, bootstrap_enabled_default, bootstrap_score_default = (
        _load_llm_defaults()
    )
    tail = int(memory_tail) if memory_tail is not None else int(tail_default)
    if tail <= 0:
        tail = tail_default
    bootstrap_on = (
        bool(bootstrap_enabled)
        if bootstrap_enabled is not None
        else bool(bootstrap_enabled_default)
    )
    bootstrap_value = (
        float(bootstrap_score)
        if bootstrap_score is not None
        else float(bootstrap_score_default)
    )

    llm_conn = connect_llm_vg_db(llm_db_path)
    markers_conn = connect_markers_db(markers_db_path)
    try:
        initialize_llm_vg_db(llm_conn)
        initialize_markers_db(markers_conn)
        policy_id, policy_name_resolved, mode, points = _get_policy(
            llm_conn, policy_name
        )

        current_rows = llm_conn.execute(
            """
            SELECT canonical_model, ticker, predicted_value, raw_model_label
            FROM llm_predictions
            WHERE forecast_date = ?
            ORDER BY canonical_model, ticker
            """,
            (date_norm,),
        ).fetchall()
        if not current_rows:
            raise ValueError(
                f"No LLM prediction rows found for forecast_date={date_norm}"
            )

        current_markers = markers_conn.execute(
            """
            SELECT ticker, marker_value
            FROM marker_values
            WHERE forecast_date = ? AND marker_name = ?
            """,
            (date_norm, str(marker_name_for_scoring)),
        ).fetchall()
        marker_map_current: Dict[str, float] = {}
        for r in current_markers:
            mv = _to_float_or_none(r["marker_value"])
            if mv is not None:
                marker_map_current[str(r["ticker"])] = mv

        models = _ordered_labels(
            [str(r["canonical_model"]) for r in current_rows], LLM_MODEL_ORDER_DEFAULT
        )
        tickers = _ordered_labels(
            [str(r["ticker"]) for r in current_rows], TICKER_ORDER_DEFAULT
        )

        predicted: Dict[str, Dict[str, Optional[float]]] = {
            m: {t: None for t in tickers} for m in models
        }
        violet: Dict[str, Dict[str, Optional[float]]] = {
            m: {t: None for t in tickers} for m in models
        }
        blue: Dict[str, Dict[str, Optional[float]]] = {
            m: {t: None for t in tickers} for m in models
        }

        for r in current_rows:
            model = str(r["canonical_model"])
            ticker = str(r["ticker"])
            pred = _to_float_or_none(r["predicted_value"])
            predicted[model][ticker] = pred
            actual = marker_map_current.get(ticker)
            if pred is None or actual is None or abs(actual) <= 0:
                continue
            acc = 100.0 - abs((actual - pred) / actual * 100.0)
            violet[model][ticker] = float(acc)
            blue[model][ticker] = _transform_accuracy(float(acc), mode, points)

        history_pred_rows = llm_conn.execute(
            """
            SELECT forecast_date, canonical_model, ticker, predicted_value
            FROM llm_predictions
            WHERE forecast_date < ?
            ORDER BY forecast_date DESC
            """,
            (date_norm,),
        ).fetchall()

        history_marker_rows = markers_conn.execute(
            """
            SELECT forecast_date, ticker, marker_value
            FROM marker_values
            WHERE marker_name = ?
            """,
            (str(marker_name_for_scoring),),
        ).fetchall()
        marker_hist_map: Dict[Tuple[str, str], float] = {}
        for r in history_marker_rows:
            mv = _to_float_or_none(r["marker_value"])
            if mv is not None:
                marker_hist_map[(str(r["forecast_date"]), str(r["ticker"]))] = mv

        hist_scores: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        for r in history_pred_rows:
            model = str(r["canonical_model"])
            ticker = str(r["ticker"])
            key = (model, ticker)
            if len(hist_scores[key]) >= tail:
                continue
            pred = _to_float_or_none(r["predicted_value"])
            if pred is None:
                continue
            actual = marker_hist_map.get((str(r["forecast_date"]), ticker))
            if actual is None or abs(actual) <= 0:
                continue
            acc = 100.0 - abs((actual - pred) / actual * 100.0)
            tr = _transform_accuracy(float(acc), mode, points)
            if tr is None:
                continue
            hist_scores[key].append(float(tr))

        green: Dict[str, Dict[str, Optional[float]]] = {
            m: {t: None for t in tickers} for m in models
        }
        green_meta: Dict[str, Dict[str, Dict[str, int]]] = {
            m: {t: {"real_rounds_used": 0, "bootstrap_slots_used": 0} for t in tickers}
            for m in models
        }

        cells_green_real = 0
        cells_green_bootstrap = 0
        for m in models:
            for t in tickers:
                vals = list(hist_scores.get((m, t), []))
                real_count = len(vals)
                bootstrap_count = 0
                if bootstrap_on and real_count < tail:
                    bootstrap_count = tail - real_count
                    vals.extend([bootstrap_value] * bootstrap_count)
                if vals:
                    green[m][t] = float(sum(vals) / len(vals))
                green_meta[m][t]["real_rounds_used"] = int(real_count)
                green_meta[m][t]["bootstrap_slots_used"] = int(bootstrap_count)
                if real_count > 0:
                    cells_green_real += 1
                if bootstrap_count > 0:
                    cells_green_bootstrap += 1

        def _row_avr(
            table: Dict[str, Dict[str, Optional[float]]],
        ) -> Dict[str, Optional[float]]:
            out: Dict[str, Optional[float]] = {}
            for model in models:
                vals = [v for v in table[model].values() if v is not None]
                out[model] = float(sum(vals) / len(vals)) if vals else None
            return out

        run_ts = _now_ts()
        llm_conn.execute(
            """
            INSERT INTO materialization_runs(
                forecast_date,
                policy_id,
                policy_name,
                marker_name,
                memory_tail,
                bootstrap_enabled,
                bootstrap_score,
                cells_total,
                cells_green_real,
                cells_green_bootstrap,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_norm,
                int(policy_id),
                str(policy_name_resolved),
                str(marker_name_for_scoring),
                int(tail),
                1 if bootstrap_on else 0,
                float(bootstrap_value),
                int(len(models) * len(tickers)),
                int(cells_green_real),
                int(cells_green_bootstrap),
                run_ts,
            ),
        )
        llm_conn.commit()

        return {
            "forecast_date": date_norm,
            "policy_id": int(policy_id),
            "policy_name": str(policy_name_resolved),
            "policy_mode": str(mode),
            "marker_name": str(marker_name_for_scoring),
            "memory_tail": int(tail),
            "bootstrap_enabled": bool(bootstrap_on),
            "bootstrap_score": float(bootstrap_value),
            "models": models,
            "tickers": tickers,
            "predicted": predicted,
            "violet": violet,
            "blue": blue,
            "green": green,
            "green_meta": green_meta,
            "row_avr": {
                "violet": _row_avr(violet),
                "blue": _row_avr(blue),
                "green": _row_avr(green),
            },
            "generated_at": run_ts,
        }
    finally:
        llm_conn.close()
        markers_conn.close()


def format_matrix_csv(
    table: Dict[str, Dict[str, Optional[float]]],
    models: Sequence[str],
    tickers: Sequence[str],
) -> str:
    out_rows = ["model," + ",".join(tickers)]
    for model in models:
        vals: List[str] = []
        for ticker in tickers:
            v = table.get(model, {}).get(ticker)
            vals.append("" if v is None else f"{float(v):.6f}")
        out_rows.append(model + "," + ",".join(vals))
    return "\n".join(out_rows) + "\n"


__all__ = [
    "LLM_VG_SCHEMA_VERSION",
    "MARKERS_SCHEMA_VERSION",
    "DEFAULT_POLICY_NAME",
    "LLM_MODEL_ORDER_DEFAULT",
    "TICKER_ORDER_DEFAULT",
    "MARKER_CLOSE_YAHOO",
    "MARKER_CLOSE_INVESTING",
    "MARKER_CLOSE_ANCHOR",
    "MARKER_CLOSE_REAL_TPLUS3",
    "resolve_llm_vg_db_path",
    "resolve_markers_db_path",
    "connect_llm_vg_db",
    "connect_markers_db",
    "initialize_llm_vg_db",
    "initialize_markers_db",
    "seed_default_aliases",
    "canonicalize_model_label",
    "parse_llm_model_table",
    "parse_markers_table",
    "ingest_llm_model_table_from_markdown",
    "ingest_markers_from_markdown",
    "materialize_llm_vbg_for_date",
    "format_matrix_csv",
]
