from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.config import paths


VG_SCHEMA_VERSION = "ml-vg-v1"
DEFAULT_POLICY_NAME = "value_assign_v1"

MODEL_ORDER_DEFAULT: Sequence[str] = (
    "Torch",
    "DYNAMIX",
    "ARIMAX",
    "PCE",
    "LSTM",
    "GARCH",
    "VAR",
    "RW",
    "ETS",
)

TICKER_ORDER_DEFAULT: Sequence[str] = ("TNX", "DJI", "SPX", "VIX", "QQQ", "AAPL")

SCORE_STATUSES: Tuple[str, ...] = (
    "scored",
    "pending_actual",
    "actual_missing",
    "model_unavailable",
    "nan_pred",
    "no_expected_date",
)


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        txt = str(value).strip()
        if txt == "" or txt.lower() in {"nan", "none", "null", "-"}:
            return None
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


def _most_common(values: Iterable[str]) -> str:
    normalized = [v for v in values if v]
    if not normalized:
        return ""
    counts = Counter(normalized)
    return counts.most_common(1)[0][0]


def _load_vbg_defaults() -> Tuple[int, bool, float, str]:
    tail = 4
    bootstrap_enabled = True
    bootstrap_score = 99.0
    real_data_start = "2025-07-29"
    try:
        import Constants as C  # type: ignore

        tail = int(getattr(C, "VBG_MEMORY_TAIL", tail))
        bootstrap_enabled = bool(getattr(C, "VBG_BOOTSTRAP_ENABLED", bootstrap_enabled))
        bootstrap_score = float(getattr(C, "VBG_BOOTSTRAP_SCORE", bootstrap_score))
        real_data_start = str(getattr(C, "VBG_REAL_DATA_START_DATE", real_data_start))
    except Exception:
        pass

    if tail <= 0:
        tail = 4
    real_data_start_norm = _to_date_or_none(real_data_start) or "2025-07-29"
    return tail, bootstrap_enabled, bootstrap_score, real_data_start_norm


def resolve_vg_db_path(db_path: Optional[Path] = None) -> Path:
    env = os.getenv("FIN_ML_VG_DB", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if db_path is not None:
        return Path(db_path).expanduser().resolve()
    try:
        import Constants as C  # type: ignore

        cfg = str(getattr(C, "VBG_DB_FILE", "")).strip()
        if cfg:
            return Path(cfg).expanduser().resolve()
    except Exception:
        pass
    return paths.OUT_I_CALC_ML_VG_DB_PATH.resolve()


def connect_vg_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    p = resolve_vg_db_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_vg_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rounds (
            forecast_date TEXT PRIMARY KEY,
            round_id TEXT NOT NULL UNIQUE,
            round_state TEXT NOT NULL,
            expected_actual_date TEXT,
            actual_lookup_date TEXT,
            run_mode TEXT,
            generated_at TEXT,
            finalized_at TEXT,
            source_context_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(length(forecast_date) = 10)
        );

        CREATE TABLE IF NOT EXISTS violet_scores (
            forecast_date TEXT NOT NULL,
            model TEXT NOT NULL,
            ticker TEXT NOT NULL,
            accuracy_pct REAL,
            score_status TEXT NOT NULL,
            source_round_id TEXT NOT NULL,
            source_partial_scores_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (forecast_date, model, ticker),
            FOREIGN KEY (forecast_date) REFERENCES rounds(forecast_date) ON DELETE CASCADE
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

        CREATE TABLE IF NOT EXISTS materialized_scores (
            run_id INTEGER NOT NULL,
            forecast_date TEXT NOT NULL,
            table_name TEXT NOT NULL,
            model TEXT NOT NULL,
            ticker TEXT NOT NULL,
            score_value REAL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (forecast_date, table_name, model, ticker),
            FOREIGN KEY (run_id) REFERENCES materialization_runs(run_id) ON DELETE CASCADE,
            CHECK(table_name IN ('violet', 'blue', 'green'))
        );

        CREATE INDEX IF NOT EXISTS idx_rounds_round_id ON rounds(round_id);
        CREATE INDEX IF NOT EXISTS idx_violet_forecast ON violet_scores(forecast_date);
        CREATE INDEX IF NOT EXISTS idx_violet_model_ticker ON violet_scores(model, ticker, forecast_date);
        CREATE INDEX IF NOT EXISTS idx_materialized_scores_ftm
        ON materialized_scores(forecast_date, table_name, model, ticker);
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
        (VG_SCHEMA_VERSION, now),
    )
    conn.commit()


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
    out = sorted(dedup.items(), key=lambda t: t[0])
    return out


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

    clean_points: List[Tuple[float, float]] = []
    last_x: Optional[float] = None
    for x, y in sorted((float(a), float(b)) for a, b in points):
        if last_x is not None and x < last_x:
            raise ValueError("Transform points must be sorted ascending by x_value")
        clean_points.append((x, y))
        last_x = x

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
        [
            (policy_id, idx, float(x), float(y))
            for idx, (x, y) in enumerate(clean_points)
        ],
    )

    if set_active:
        conn.execute(
            "UPDATE transform_policies SET is_active = CASE WHEN policy_id = ? THEN 1 ELSE 0 END",
            (policy_id,),
        )

    conn.commit()
    return policy_id


def ensure_default_transform_policy(conn: sqlite3.Connection) -> int:
    points = _load_mapping_points_from_csv()
    return upsert_transform_policy(
        conn,
        policy_name=DEFAULT_POLICY_NAME,
        mode="step_floor",
        points=points,
        set_active=True,
    )


def upsert_round(
    conn: sqlite3.Connection,
    *,
    forecast_date: str,
    round_id: str,
    round_state: str,
    expected_actual_date: str,
    actual_lookup_date: str,
    run_mode: str,
    generated_at: str,
    finalized_at: str,
    source_context_path: str,
) -> None:
    now = _now_ts()
    conn.execute(
        """
        INSERT INTO rounds(
            forecast_date,
            round_id,
            round_state,
            expected_actual_date,
            actual_lookup_date,
            run_mode,
            generated_at,
            finalized_at,
            source_context_path,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_date) DO UPDATE SET
            round_id=excluded.round_id,
            round_state=excluded.round_state,
            expected_actual_date=excluded.expected_actual_date,
            actual_lookup_date=excluded.actual_lookup_date,
            run_mode=excluded.run_mode,
            generated_at=excluded.generated_at,
            finalized_at=excluded.finalized_at,
            source_context_path=excluded.source_context_path,
            updated_at=excluded.updated_at
        """,
        (
            str(forecast_date),
            str(round_id),
            str(round_state),
            str(expected_actual_date),
            str(actual_lookup_date),
            str(run_mode),
            str(generated_at),
            str(finalized_at),
            str(source_context_path),
            now,
            now,
        ),
    )


def upsert_violet_scores(
    conn: sqlite3.Connection,
    *,
    forecast_date: str,
    source_round_id: str,
    source_partial_scores_path: str,
    rows: Sequence[Dict[str, Any]],
) -> int:
    now = _now_ts()
    payload: List[Tuple[Any, ...]] = []
    for row in rows:
        model = str(row.get("model", "")).strip()
        ticker = str(row.get("ticker", "")).strip()
        score_status = str(row.get("score_status", "")).strip() or "pending_actual"
        if model == "" or ticker == "":
            continue
        if score_status not in SCORE_STATUSES:
            score_status = "pending_actual"
        payload.append(
            (
                str(forecast_date),
                model,
                ticker,
                _to_float_or_none(row.get("accuracy_pct")),
                score_status,
                str(source_round_id),
                str(source_partial_scores_path),
                now,
                now,
            )
        )

    conn.executemany(
        """
        INSERT INTO violet_scores(
            forecast_date,
            model,
            ticker,
            accuracy_pct,
            score_status,
            source_round_id,
            source_partial_scores_path,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_date, model, ticker) DO UPDATE SET
            accuracy_pct=excluded.accuracy_pct,
            score_status=excluded.score_status,
            source_round_id=excluded.source_round_id,
            source_partial_scores_path=excluded.source_partial_scores_path,
            updated_at=excluded.updated_at
        """,
        payload,
    )
    return len(payload)


def ingest_round_from_artifacts(
    round_id: str, db_path: Optional[Path] = None
) -> Dict[str, Any]:
    context_path = (
        paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR / str(round_id) / "round_context.json"
    )
    partial_scores_path = (
        paths.OUT_I_CALC_FOLLOWUP_ML_SCORES_DIR / f"{round_id}_partial_scores.csv"
    )

    if not context_path.exists():
        raise FileNotFoundError(f"Missing context file: {context_path}")
    if not partial_scores_path.exists():
        raise FileNotFoundError(f"Missing partial scores file: {partial_scores_path}")

    context = json.loads(context_path.read_text(encoding="utf-8"))
    rows: List[Dict[str, Any]] = []
    with partial_scores_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    if not rows:
        raise ValueError(f"No rows found in partial scores: {partial_scores_path}")

    forecast_dates = [_to_date_or_none(r.get("forecast_date")) or "" for r in rows]
    expected_dates = [
        _to_date_or_none(r.get("expected_actual_date")) or "" for r in rows
    ]
    lookup_dates = [_to_date_or_none(r.get("lookup_actual_date")) or "" for r in rows]

    forecast_date = _most_common(forecast_dates)
    if forecast_date == "":
        raise ValueError(f"Unable to resolve forecast_date from {partial_scores_path}")

    expected_actual_date = _most_common(expected_dates)
    lookup_override = ""
    actuals_meta = context.get("actuals")
    if isinstance(actuals_meta, dict):
        lookup_override = (
            _to_date_or_none(actuals_meta.get("lookup_date_override")) or ""
        )
    actual_lookup_date = lookup_override or _most_common(lookup_dates)

    round_state = str(context.get("round_state", ""))
    run_mode = str(context.get("run_mode", "strict_production"))
    generated_at = str(context.get("generated_at", ""))
    finalized_at = str(context.get("finalized_at", ""))

    conn = connect_vg_db(db_path)
    try:
        initialize_vg_db(conn)
        ensure_default_transform_policy(conn)
        upsert_round(
            conn,
            forecast_date=forecast_date,
            round_id=str(round_id),
            round_state=round_state,
            expected_actual_date=expected_actual_date,
            actual_lookup_date=actual_lookup_date,
            run_mode=run_mode,
            generated_at=generated_at,
            finalized_at=finalized_at,
            source_context_path=str(context_path.resolve()),
        )
        upserted = upsert_violet_scores(
            conn,
            forecast_date=forecast_date,
            source_round_id=str(round_id),
            source_partial_scores_path=str(partial_scores_path.resolve()),
            rows=rows,
        )
        conn.commit()
    finally:
        conn.close()

    scored_rows = sum(
        1 for r in rows if str(r.get("score_status", "")).strip() == "scored"
    )
    return {
        "round_id": str(round_id),
        "forecast_date": forecast_date,
        "rows_total": len(rows),
        "rows_scored": scored_rows,
        "rows_upserted": upserted,
        "db_path": str(resolve_vg_db_path(db_path)),
    }


def _get_policy(
    conn: sqlite3.Connection, policy_name: Optional[str]
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
    points_rows = conn.execute(
        "SELECT x_value, y_value FROM transform_points WHERE policy_id = ? ORDER BY point_order",
        (policy_id,),
    ).fetchall()
    if not points_rows:
        raise RuntimeError(f"No transform points found for policy_id={policy_id}")

    points = [(float(r["x_value"]), float(r["y_value"])) for r in points_rows]
    return policy_id, str(row["policy_name"]), str(row["mode"]), points


def _transform_accuracy(
    accuracy_pct: Optional[float], mode: str, points: Sequence[Tuple[float, float]]
) -> Optional[float]:
    if accuracy_pct is None:
        return None
    x = float(accuracy_pct)
    if not points:
        return x

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


def _ordered_labels(
    rows: Sequence[sqlite3.Row], key: str, preferred: Sequence[str]
) -> List[str]:
    seen = {str(r[key]) for r in rows}
    ordered = [x for x in preferred if x in seen]
    extras = sorted(x for x in seen if x not in set(preferred))
    return ordered + extras


def materialize_vbg_for_date(
    forecast_date: str,
    *,
    db_path: Optional[Path] = None,
    policy_name: Optional[str] = None,
    memory_tail: Optional[int] = None,
    bootstrap_enabled: Optional[bool] = None,
    bootstrap_score: Optional[float] = None,
) -> Dict[str, Any]:
    date_norm = _to_date_or_none(forecast_date)
    if not date_norm:
        raise ValueError(f"Invalid forecast_date: {forecast_date!r}")

    (
        tail_default,
        bootstrap_enabled_default,
        bootstrap_score_default,
        real_data_start_date,
    ) = _load_vbg_defaults()
    tail = int(memory_tail) if memory_tail is not None else int(tail_default)
    if tail <= 0:
        tail = tail_default
    bootstrap_on = (
        bool(bootstrap_enabled)
        if bootstrap_enabled is not None
        else bootstrap_enabled_default
    )
    bootstrap_value = (
        float(bootstrap_score)
        if bootstrap_score is not None
        else float(bootstrap_score_default)
    )

    conn = connect_vg_db(db_path)
    try:
        initialize_vg_db(conn)
        if not policy_name or str(policy_name).strip() == DEFAULT_POLICY_NAME:
            ensure_default_transform_policy(conn)
        policy_id, policy_name_resolved, mode, points = _get_policy(conn, policy_name)

        current_rows = conn.execute(
            """
            SELECT model, ticker, accuracy_pct, score_status
            FROM violet_scores
            WHERE forecast_date = ?
            ORDER BY model, ticker
            """,
            (date_norm,),
        ).fetchall()
        if not current_rows:
            raise ValueError(f"No violet rows found for forecast_date={date_norm}")

        models = _ordered_labels(current_rows, "model", MODEL_ORDER_DEFAULT)
        tickers = _ordered_labels(current_rows, "ticker", TICKER_ORDER_DEFAULT)

        violet: Dict[str, Dict[str, Optional[float]]] = {
            m: {t: None for t in tickers} for m in models
        }
        blue: Dict[str, Dict[str, Optional[float]]] = {
            m: {t: None for t in tickers} for m in models
        }

        for r in current_rows:
            model = str(r["model"])
            ticker = str(r["ticker"])
            acc = _to_float_or_none(r["accuracy_pct"])
            status = str(r["score_status"])
            violet[model][ticker] = acc
            if status == "scored":
                blue[model][ticker] = _transform_accuracy(acc, mode, points)

        history_rows = conn.execute(
            """
            SELECT forecast_date, model, ticker, accuracy_pct, score_status
            FROM violet_scores
            WHERE forecast_date < ? AND forecast_date >= ?
            ORDER BY forecast_date DESC
            """,
            (date_norm, real_data_start_date),
        ).fetchall()

        hist_scores: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        for r in history_rows:
            key = (str(r["model"]), str(r["ticker"]))
            if len(hist_scores[key]) >= tail:
                continue
            if str(r["score_status"]) != "scored":
                continue
            acc = _to_float_or_none(r["accuracy_pct"])
            tr = _transform_accuracy(acc, mode, points)
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

                green_meta[m][t]["real_rounds_used"] = real_count
                green_meta[m][t]["bootstrap_slots_used"] = bootstrap_count
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
        conn.execute(
            """
            INSERT INTO materialization_runs(
                forecast_date,
                policy_id,
                policy_name,
                memory_tail,
                bootstrap_enabled,
                bootstrap_score,
                cells_total,
                cells_green_real,
                cells_green_bootstrap,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_norm,
                policy_id,
                policy_name_resolved,
                int(tail),
                1 if bootstrap_on else 0,
                float(bootstrap_value),
                int(len(models) * len(tickers)),
                int(cells_green_real),
                int(cells_green_bootstrap),
                run_ts,
            ),
        )

        run_id_row = conn.execute("SELECT last_insert_rowid() AS run_id").fetchone()
        if run_id_row is None:
            raise RuntimeError("Failed to resolve materialization run_id")
        run_id = int(run_id_row["run_id"])

        conn.execute(
            "DELETE FROM materialized_scores WHERE forecast_date = ?",
            (date_norm,),
        )

        rows_to_write: List[Tuple[int, str, str, str, str, Optional[float], str]] = []
        # Persistence policy: store only violet and green snapshots.
        # Blue is derived on-demand from violet via active transform policy.
        for table_name, table in (("violet", violet), ("green", green)):
            for model in models:
                for ticker in tickers:
                    rows_to_write.append(
                        (
                            run_id,
                            date_norm,
                            table_name,
                            model,
                            ticker,
                            table.get(model, {}).get(ticker),
                            run_ts,
                        )
                    )

        conn.executemany(
            """
            INSERT INTO materialized_scores(
                run_id, forecast_date, table_name, model, ticker, score_value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_write,
        )

        conn.commit()

        return {
            "run_id": run_id,
            "forecast_date": date_norm,
            "policy_id": policy_id,
            "policy_name": policy_name_resolved,
            "policy_mode": mode,
            "memory_tail": int(tail),
            "bootstrap_enabled": bool(bootstrap_on),
            "bootstrap_score": float(bootstrap_value),
            "models": models,
            "tickers": tickers,
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
            "real_data_start_date": real_data_start_date,
            "materialized_rows_written": len(rows_to_write),
        }
    finally:
        conn.close()


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


def write_vg_debug_log(
    *,
    stage: str,
    payload: Dict[str, Any],
    root_dir: Optional[Path] = None,
    trace_id: Optional[str] = None,
) -> Path:
    base = (root_dir or (paths.OUT_I_CALC_DIR / "gui_ops" / "vg")).resolve()
    base.mkdir(parents=True, exist_ok=True)

    clean_stage = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(stage)
    )
    clean_stage = clean_stage or "stage"
    trace = str(trace_id or f"VG-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = base / f"{stamp}_{trace}_{clean_stage}.json"

    doc: Dict[str, Any] = {
        "trace_id": trace,
        "stage": str(stage),
        "generated_at": _now_ts(),
    }
    doc.update(dict(payload))
    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out_path


def seed_dummy_green_snapshots(
    *,
    db_path: Optional[Path] = None,
    snapshots: Optional[Sequence[Tuple[str, float]]] = None,
    policy_name: str = "debug_seed_green_v1",
    models: Optional[Sequence[str]] = None,
    tickers: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    use_snapshots = list(
        snapshots
        if snapshots is not None
        else [
            ("2000-01-03", 99.1),
            ("2000-01-10", 99.2),
            ("2000-01-17", 99.3),
            ("2000-01-24", 99.4),
        ]
    )
    if not use_snapshots:
        raise ValueError("snapshots cannot be empty")

    model_labels = [str(x) for x in (models or MODEL_ORDER_DEFAULT)]
    ticker_labels = [str(x) for x in (tickers or TICKER_ORDER_DEFAULT)]
    if not model_labels or not ticker_labels:
        raise ValueError("models and tickers must be non-empty")

    normalized: List[Tuple[str, float]] = []
    for raw_date, raw_value in use_snapshots:
        date_norm = _to_date_or_none(raw_date)
        if not date_norm:
            raise ValueError(f"Invalid snapshot date: {raw_date!r}")
        normalized.append((date_norm, float(raw_value)))

    conn = connect_vg_db(db_path)
    try:
        initialize_vg_db(conn)
        policy_id = upsert_transform_policy(
            conn,
            policy_name=str(policy_name),
            mode="piecewise_linear",
            points=_load_mapping_points_from_csv(),
            set_active=False,
        )

        rows_per_date = int(len(model_labels) * len(ticker_labels))
        created_dates: List[str] = []
        per_date_rows: Dict[str, int] = {}

        for forecast_date, score_value in normalized:
            run_ts = _now_ts()
            conn.execute(
                "DELETE FROM materialized_scores WHERE forecast_date = ? AND table_name = 'green'",
                (forecast_date,),
            )
            conn.execute(
                """
                INSERT INTO materialization_runs(
                    forecast_date,
                    policy_id,
                    policy_name,
                    memory_tail,
                    bootstrap_enabled,
                    bootstrap_score,
                    cells_total,
                    cells_green_real,
                    cells_green_bootstrap,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast_date,
                    policy_id,
                    str(policy_name),
                    4,
                    1,
                    float(score_value),
                    rows_per_date,
                    0,
                    rows_per_date,
                    run_ts,
                ),
            )
            run_id_row = conn.execute("SELECT last_insert_rowid() AS run_id").fetchone()
            if run_id_row is None:
                raise RuntimeError("Failed to resolve run id for dummy green snapshot")
            run_id = int(run_id_row["run_id"])

            payload: List[Tuple[int, str, str, str, str, float, str]] = []
            for model in model_labels:
                for ticker in ticker_labels:
                    payload.append(
                        (
                            run_id,
                            forecast_date,
                            "green",
                            str(model),
                            str(ticker),
                            float(score_value),
                            run_ts,
                        )
                    )
            conn.executemany(
                """
                INSERT INTO materialized_scores(
                    run_id, forecast_date, table_name, model, ticker, score_value, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            created_dates.append(forecast_date)
            per_date_rows[forecast_date] = len(payload)

        conn.commit()
    finally:
        conn.close()

    return {
        "db_path": str(resolve_vg_db_path(db_path)),
        "policy_name": str(policy_name),
        "dates_seeded": created_dates,
        "rows_per_date": rows_per_date,
        "rows_written_by_date": per_date_rows,
        "models_count": len(model_labels),
        "tickers_count": len(ticker_labels),
    }


__all__ = [
    "VG_SCHEMA_VERSION",
    "DEFAULT_POLICY_NAME",
    "MODEL_ORDER_DEFAULT",
    "TICKER_ORDER_DEFAULT",
    "resolve_vg_db_path",
    "connect_vg_db",
    "initialize_vg_db",
    "upsert_transform_policy",
    "ensure_default_transform_policy",
    "ingest_round_from_artifacts",
    "materialize_vbg_for_date",
    "format_matrix_csv",
    "write_vg_debug_log",
    "seed_dummy_green_snapshots",
]
