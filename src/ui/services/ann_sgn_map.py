from __future__ import annotations

import csv
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from src.config import paths
from src.ui.services.ann_feature_store import FAMILY_TABLES
from src.ui.services.vg_loader import build_ann_real_vs_computed_rows


SGN_CLASS_ORDER: tuple[str, ...] = ("pp", "pn", "np", "nn")
SGN_CLASS_LABELS: dict[str, str] = {
    "pp": "real:+ computed:+",
    "pn": "real:+ computed:-",
    "np": "real:- computed:+",
    "nn": "real:- computed:-",
}


def _normalize_computed_sgn(value: str) -> str | None:
    raw = str(value or "").strip()
    if raw in {"+", "+1", "1", "pos", "positive"}:
        return "+1"
    if raw in {"-", "-1", "neg", "negative"}:
        return "-1"
    return None


def conditional_real_probabilities(
    *, computed_sgn: str, class_probabilities: dict[str, float]
) -> dict[str, Any]:
    normalized = _normalize_computed_sgn(computed_sgn)
    if normalized is None:
        return {
            "available": False,
            "computed_sgn": "",
            "p_real_pos": 0.0,
            "p_real_neg": 0.0,
            "fallback_used": False,
            "reason": "computed_sgn_unavailable",
        }

    if normalized == "+1":
        p_real_pos_raw = float(class_probabilities.get("pp", 0.0))
        p_real_neg_raw = float(class_probabilities.get("np", 0.0))
    else:
        p_real_pos_raw = float(class_probabilities.get("pn", 0.0))
        p_real_neg_raw = float(class_probabilities.get("nn", 0.0))

    denom = p_real_pos_raw + p_real_neg_raw
    if denom <= 1e-12:
        return {
            "available": True,
            "computed_sgn": normalized,
            "p_real_pos": 0.5,
            "p_real_neg": 0.5,
            "fallback_used": True,
            "reason": "zero_denominator",
        }

    return {
        "available": True,
        "computed_sgn": normalized,
        "p_real_pos": float(p_real_pos_raw / denom),
        "p_real_neg": float(p_real_neg_raw / denom),
        "fallback_used": False,
        "reason": "",
    }


def suggested_real_sgn(
    *, conditional_payload: dict[str, Any], low_confidence_threshold: float = 0.60
) -> dict[str, Any]:
    if not bool(conditional_payload.get("available")):
        return {
            "available": False,
            "value": "N/A",
            "confidence": 0.0,
            "low_confidence": True,
            "reason": str(
                conditional_payload.get("reason") or "computed_sgn_unavailable"
            ),
        }

    p_real_pos = float(conditional_payload.get("p_real_pos") or 0.0)
    p_real_neg = float(conditional_payload.get("p_real_neg") or 0.0)
    value = "+1" if p_real_pos >= p_real_neg else "-1"
    confidence = max(p_real_pos, p_real_neg)
    return {
        "available": True,
        "value": value,
        "confidence": float(confidence),
        "low_confidence": bool(confidence < float(low_confidence_threshold)),
        "reason": "",
    }


def classify_sgn_case(*, real_sgn: str, computed_sgn: str) -> str | None:
    real = str(real_sgn or "").strip()
    computed = str(computed_sgn or "").strip()
    if real not in {"+", "-"} or computed not in {"+", "-"}:
        return None
    return ("p" if real == "+" else "n") + ("p" if computed == "+" else "n")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return values[0]
    if q >= 1:
        return values[-1]
    idx = (len(values) - 1) * q
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def _robust_stats(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    sorted_values = sorted(values)
    med = median(sorted_values)
    q1 = _percentile(sorted_values, 0.25)
    q3 = _percentile(sorted_values, 0.75)
    iqr = q3 - q1
    if iqr > 1e-12:
        return med, iqr
    lo = sorted_values[0]
    hi = sorted_values[-1]
    fallback = hi - lo
    if fallback > 1e-12:
        return med, fallback
    return med, 1.0


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for xv, yv in zip(x, y):
        dx = xv - mean_x
        dy = yv - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy
    if var_x <= 1e-12 or var_y <= 1e-12:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def _macro_f1(true_labels: list[str], pred_labels: list[str]) -> float:
    if len(true_labels) != len(pred_labels) or not true_labels:
        return 0.0
    f1_values: list[float] = []
    for cls in SGN_CLASS_ORDER:
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == cls and p != cls)
        precision = tp / (tp + fp) if tp + fp > 0 else 0.0
        recall = tp / (tp + fn) if tp + fn > 0 else 0.0
        if precision + recall <= 1e-12:
            f1_values.append(0.0)
        else:
            f1_values.append((2.0 * precision * recall) / (precision + recall))
    return sum(f1_values) / len(f1_values)


def _argmax_class(prob: dict[str, float]) -> str:
    best = SGN_CLASS_ORDER[0]
    best_score = float(prob.get(best, 0.0))
    for cls in SGN_CLASS_ORDER[1:]:
        score = float(prob.get(cls, 0.0))
        if score > best_score:
            best = cls
            best_score = score
    return best


def _build_feature_stats(
    samples: list[dict[str, Any]],
) -> dict[str, tuple[float, float]]:
    values_by_feature: dict[str, list[float]] = {}
    for sample in samples:
        features = sample.get("features")
        if not isinstance(features, dict):
            continue
        for name, raw in features.items():
            value = _safe_float(raw)
            if value is None:
                continue
            values_by_feature.setdefault(str(name), []).append(value)
    stats: dict[str, tuple[float, float]] = {}
    for name, values in values_by_feature.items():
        stats[name] = _robust_stats(values)
    return stats


def _normalized_feature_values(
    samples: list[dict[str, Any]],
    stats: dict[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sample in samples:
        features = (
            sample.get("features") if isinstance(sample.get("features"), dict) else {}
        )
        norm: dict[str, float] = {}
        for name, (med, scale) in stats.items():
            value = _safe_float(features.get(name))
            if value is None:
                continue
            z = (value - med) / (scale if abs(scale) > 1e-12 else 1.0)
            if z > 8.0:
                z = 8.0
            elif z < -8.0:
                z = -8.0
            norm[name] = z
        clone = dict(sample)
        clone["_norm"] = norm
        out.append(clone)
    return out


def _feature_utility(samples: list[dict[str, Any]], feature_name: str) -> float:
    by_class: dict[str, list[float]] = {k: [] for k in SGN_CLASS_ORDER}
    for sample in samples:
        cls = str(sample.get("class_id") or "")
        if cls not in by_class:
            continue
        norm = sample.get("_norm")
        if not isinstance(norm, dict):
            continue
        value = _safe_float(norm.get(feature_name))
        if value is None:
            continue
        by_class[cls].append(value)
    means: list[float] = []
    counts: list[int] = []
    for cls in SGN_CLASS_ORDER:
        bucket = by_class[cls]
        if not bucket:
            continue
        means.append(sum(bucket) / len(bucket))
        counts.append(len(bucket))
    if len(means) < 2:
        return 0.0
    mean_of_means = sum(means) / len(means)
    between = sum((x - mean_of_means) ** 2 for x in means) / len(means)
    coverage = min(counts) / max(counts) if counts and max(counts) > 0 else 0.0
    return math.sqrt(between) * max(coverage, 0.2)


def _rolling_stability(
    samples: list[dict[str, Any]],
    feature_name: str,
    rolling_window: int,
) -> float:
    if rolling_window < 3 or len(samples) < rolling_window + 2:
        return 0.0
    ordered = sorted(samples, key=lambda row: str(row.get("as_of_date") or ""))
    values: list[float] = []
    for idx in range(rolling_window, len(ordered) + 1):
        window = ordered[idx - rolling_window : idx]
        util = _feature_utility(window, feature_name)
        if util > 0:
            values.append(util)
    if len(values) < 2:
        return 0.0
    mean_val = sum(values) / len(values)
    variance = sum((x - mean_val) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def _select_weighted_axes(
    samples: list[dict[str, Any]],
    *,
    max_features: int,
    rolling_window: int,
    corr_threshold: float,
) -> dict[str, list[dict[str, float]]]:
    feature_names: list[str] = []
    if samples:
        norm = samples[0].get("_norm")
        if isinstance(norm, dict):
            feature_names = sorted(norm.keys())

    if not feature_names:
        return {"U": [], "V": []}

    scored: list[dict[str, float]] = []
    for feature_name in feature_names:
        utility = _feature_utility(samples, feature_name)
        if utility <= 0:
            continue
        stability = _rolling_stability(samples, feature_name, rolling_window)
        score = utility / (1.0 + stability)
        scored.append(
            {
                "feature": feature_name,
                "utility": utility,
                "stability": stability,
                "score": score,
            }
        )

    scored.sort(key=lambda item: float(item["score"]), reverse=True)
    selected: list[dict[str, float]] = []
    for item in scored:
        name = str(item["feature"])
        series_candidate: list[float] = []
        for sample in samples:
            norm = sample.get("_norm")
            if not isinstance(norm, dict):
                continue
            value = _safe_float(norm.get(name))
            if value is not None:
                series_candidate.append(value)
        keep = True
        for prior in selected:
            prior_name = str(prior["feature"])
            x_vals: list[float] = []
            y_vals: list[float] = []
            for sample in samples:
                norm = sample.get("_norm")
                if not isinstance(norm, dict):
                    continue
                a = _safe_float(norm.get(name))
                b = _safe_float(norm.get(prior_name))
                if a is None or b is None:
                    continue
                x_vals.append(a)
                y_vals.append(b)
            corr = abs(_pearson(x_vals, y_vals)) if x_vals else 0.0
            if corr >= corr_threshold:
                keep = False
                break
        if not keep:
            continue
        selected.append(item)
        if len(selected) >= max_features:
            break

    axis_u: list[dict[str, float]] = []
    axis_v: list[dict[str, float]] = []
    for idx, item in enumerate(selected):
        axis = axis_u if idx % 2 == 0 else axis_v
        axis.append(item)

    if not axis_v and axis_u:
        axis_v.append(axis_u.pop())
    if not axis_u and axis_v:
        axis_u.append(axis_v.pop())

    def _normalize(items: list[dict[str, float]]) -> list[dict[str, float]]:
        denom = sum(abs(float(x["score"])) for x in items)
        if denom <= 1e-12:
            return [
                {
                    "feature": str(x["feature"]),
                    "weight": 1.0 / len(items),
                    "utility": float(x["utility"]),
                    "stability": float(x["stability"]),
                    "score": float(x["score"]),
                }
                for x in items
            ]
        out: list[dict[str, float]] = []
        for x in items:
            out.append(
                {
                    "feature": str(x["feature"]),
                    "weight": float(x["score"]) / denom,
                    "utility": float(x["utility"]),
                    "stability": float(x["stability"]),
                    "score": float(x["score"]),
                }
            )
        return out

    return {"U": _normalize(axis_u), "V": _normalize(axis_v)}


def _axis_value(norm: dict[str, float], weights: list[dict[str, float]]) -> float:
    total = 0.0
    for item in weights:
        feature = str(item.get("feature") or "")
        if not feature:
            continue
        weight = float(item.get("weight") or 0.0)
        value = _safe_float(norm.get(feature))
        if value is None:
            continue
        total += weight * value
    return total


def _normalize_feature_payload(
    feature_payload: dict[str, float],
    stats: dict[str, tuple[float, float]],
) -> dict[str, float]:
    norm: dict[str, float] = {}
    for name, (med, scale) in stats.items():
        raw = _safe_float(feature_payload.get(name))
        if raw is None:
            continue
        z = (raw - med) / (scale if abs(scale) > 1e-12 else 1.0)
        if z > 8.0:
            z = 8.0
        elif z < -8.0:
            z = -8.0
        norm[name] = z
    return norm


def _knn_probabilities(
    *,
    u: float,
    v: float,
    points: list[dict[str, Any]],
    k_neighbors: int,
    exclude_index: int | None = None,
) -> dict[str, float]:
    dists: list[tuple[float, str]] = []
    for idx, point in enumerate(points):
        if exclude_index is not None and idx == exclude_index:
            continue
        pu = _safe_float(point.get("U"))
        pv = _safe_float(point.get("V"))
        cls = str(point.get("class_id") or "")
        if pu is None or pv is None or cls not in SGN_CLASS_ORDER:
            continue
        dist = math.sqrt((u - pu) ** 2 + (v - pv) ** 2)
        dists.append((dist, cls))

    if not dists:
        base = 1.0 / len(SGN_CLASS_ORDER)
        return {cls: base for cls in SGN_CLASS_ORDER}

    dists.sort(key=lambda item: item[0])
    k = max(1, min(k_neighbors, len(dists)))
    selected = dists[:k]

    scores: dict[str, float] = {cls: 0.0 for cls in SGN_CLASS_ORDER}
    for dist, cls in selected:
        weight = 1.0 / (dist + 1e-6)
        scores[cls] += weight

    total = sum(scores.values())
    if total <= 1e-12:
        base = 1.0 / len(SGN_CLASS_ORDER)
        return {cls: base for cls in SGN_CLASS_ORDER}
    return {cls: float(scores[cls] / total) for cls in SGN_CLASS_ORDER}


def build_sgn_probability_map_from_samples(
    *,
    ticker: str,
    samples: list[dict[str, Any]],
    grid_size: int = 35,
    max_features: int = 10,
    k_neighbors: int = 9,
    edge_threshold: float = 0.60,
    rolling_window: int = 20,
    corr_threshold: float = 0.92,
) -> dict[str, Any]:
    clean_samples: list[dict[str, Any]] = []
    for sample in samples:
        cls = str(sample.get("class_id") or "")
        features = sample.get("features")
        if cls not in SGN_CLASS_ORDER or not isinstance(features, dict):
            continue
        clean_samples.append(
            {
                "as_of_date": str(sample.get("as_of_date") or ""),
                "ticker": str(sample.get("ticker") or ticker).strip().upper(),
                "class_id": cls,
                "magnitude_label": str(sample.get("magnitude_label") or ""),
                "features": dict(features),
            }
        )

    stats = _build_feature_stats(clean_samples)
    normed = _normalized_feature_values(clean_samples, stats)
    weights = _select_weighted_axes(
        normed,
        max_features=max_features,
        rolling_window=rolling_window,
        corr_threshold=corr_threshold,
    )

    points: list[dict[str, Any]] = []
    for sample in normed:
        norm = sample.get("_norm") if isinstance(sample.get("_norm"), dict) else {}
        u = _axis_value(norm, weights.get("U", []))
        v = _axis_value(norm, weights.get("V", []))
        points.append(
            {
                "as_of_date": str(sample.get("as_of_date") or ""),
                "ticker": str(sample.get("ticker") or ticker).strip().upper(),
                "class_id": str(sample.get("class_id") or ""),
                "magnitude_label": str(sample.get("magnitude_label") or ""),
                "U": u,
                "V": v,
            }
        )

    # Point-level surrogate confidence (leave-one-out).
    true_labels: list[str] = []
    pred_labels: list[str] = []
    edge_true: list[str] = []
    edge_pred: list[str] = []
    for idx, row in enumerate(points):
        prob = _knn_probabilities(
            u=float(row["U"]),
            v=float(row["V"]),
            points=points,
            k_neighbors=k_neighbors,
            exclude_index=idx,
        )
        pred = _argmax_class(prob)
        max_prob = max(float(prob.get(cls, 0.0)) for cls in SGN_CLASS_ORDER)
        row["pred_class"] = pred
        row["max_prob"] = max_prob
        for cls in SGN_CLASS_ORDER:
            row[f"prob_{cls}"] = float(prob.get(cls, 0.0))
        truth = str(row.get("class_id") or "")
        true_labels.append(truth)
        pred_labels.append(pred)
        if max_prob < edge_threshold:
            edge_true.append(truth)
            edge_pred.append(pred)

    grid: list[dict[str, Any]] = []
    if points:
        u_values = [float(x["U"]) for x in points]
        v_values = [float(x["V"]) for x in points]
        u_min = min(u_values)
        u_max = max(u_values)
        v_min = min(v_values)
        v_max = max(v_values)
        u_pad = max((u_max - u_min) * 0.05, 0.05)
        v_pad = max((v_max - v_min) * 0.05, 0.05)
        u_lo = u_min - u_pad
        u_hi = u_max + u_pad
        v_lo = v_min - v_pad
        v_hi = v_max + v_pad

        gx = max(2, int(grid_size))
        gy = max(2, int(grid_size))
        for yi in range(gy):
            v = v_lo + (v_hi - v_lo) * (yi / (gy - 1))
            for xi in range(gx):
                u = u_lo + (u_hi - u_lo) * (xi / (gx - 1))
                prob = _knn_probabilities(
                    u=u,
                    v=v,
                    points=points,
                    k_neighbors=k_neighbors,
                )
                pred = _argmax_class(prob)
                max_prob = max(float(prob.get(cls, 0.0)) for cls in SGN_CLASS_ORDER)
                row: dict[str, Any] = {
                    "U": float(u),
                    "V": float(v),
                    "pred_class": pred,
                    "max_prob": float(max_prob),
                }
                for cls in SGN_CLASS_ORDER:
                    row[f"prob_{cls}"] = float(prob.get(cls, 0.0))
                grid.append(row)

    sample_count = len(true_labels)
    correct = sum(1 for t, p in zip(true_labels, pred_labels) if t == p)
    agreement_rate = (correct / sample_count) if sample_count > 0 else 0.0
    edge_count = len(edge_true)
    edge_correct = sum(1 for t, p in zip(edge_true, edge_pred) if t == p)
    edge_accuracy = (edge_correct / edge_count) if edge_count > 0 else 0.0
    non_edge_count = sample_count - edge_count
    non_edge_accuracy = (
        (correct - edge_correct) / non_edge_count if non_edge_count > 0 else 0.0
    )

    confusion: dict[str, dict[str, int]] = {
        cls: {inner: 0 for inner in SGN_CLASS_ORDER} for cls in SGN_CLASS_ORDER
    }
    for t, p in zip(true_labels, pred_labels):
        if t in confusion and p in confusion[t]:
            confusion[t][p] += 1

    metrics = {
        "sample_count": int(sample_count),
        "agreement_rate": float(agreement_rate),
        "macro_f1": float(_macro_f1(true_labels, pred_labels)),
        "edge_threshold": float(edge_threshold),
        "edge_count": int(edge_count),
        "edge_accuracy": float(edge_accuracy),
        "non_edge_count": int(non_edge_count),
        "non_edge_accuracy": float(non_edge_accuracy),
        "diagnostic_only": bool(
            agreement_rate < 0.70 or (edge_count > 0 and edge_accuracy < 0.50)
        ),
        "confusion": confusion,
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "ticker": str(ticker or "").strip().upper(),
        "class_order": list(SGN_CLASS_ORDER),
        "class_labels": dict(SGN_CLASS_LABELS),
        "point_count": len(points),
        "points": points,
        "grid": grid,
        "weights": weights,
        "metrics": metrics,
        "contour_thresholds": [0.55, 0.70, 0.85],
    }


def _load_feature_matrix_for_ticker(
    *, store_path: Path, ticker: str
) -> dict[str, dict[str, float]]:
    if not store_path.exists():
        return {}
    ticker_u = str(ticker or "").strip().upper()
    if not ticker_u:
        return {}

    out: dict[str, dict[str, float]] = {}
    conn = sqlite3.connect(str(store_path))
    try:
        for table_name in FAMILY_TABLES.values():
            rows = conn.execute(
                f"""
                SELECT as_of_date, feature_name, feature_value, value_status
                FROM {table_name}
                WHERE ticker = ?
                """,
                (ticker_u,),
            ).fetchall()
            for as_of_date, feature_name, feature_value, value_status in rows:
                if str(value_status or "") != "present":
                    continue
                value = _safe_float(feature_value)
                if value is None:
                    continue
                date_key = str(as_of_date or "").strip()
                if not date_key:
                    continue
                out.setdefault(date_key, {})[str(feature_name)] = value
    finally:
        conn.close()
    return out


def _extract_base_feature_name(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if "::" in text:
        text = text.split("::", 1)[1]
    if "__lag" in text:
        text = text.split("__lag", 1)[0]
    return text.strip()


def _load_selected_feature_names(profile_path: Path) -> set[str]:
    if not profile_path.exists():
        return set()
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    values: list[str] = []
    if isinstance(payload, dict):
        values = [str(x) for x in list(payload.get("selected_features") or [])]
    elif isinstance(payload, list):
        values = [str(x) for x in payload]
    out = {_extract_base_feature_name(x) for x in values}
    return {x for x in out if x}


def _candidate_anchor_dates(rounds_dir: Path) -> list[str]:
    if not rounds_dir.exists():
        return []
    out: list[str] = []
    for path in sorted(rounds_dir.glob("anchor-*")):
        if not path.is_dir():
            continue
        suffix = path.name.replace("anchor-", "")
        if len(suffix) != 8 or not suffix.isdigit():
            continue
        out.append(f"{suffix[0:4]}-{suffix[4:6]}-{suffix[6:8]}")
    return sorted(set(out))


def load_sgn_samples_for_ticker(
    *,
    ticker: str,
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
    store_path: Path | None = None,
    profile_path: Path | None = None,
) -> list[dict[str, Any]]:
    use_rounds = (rounds_dir or paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR).resolve()
    use_raw = (raw_tickers_dir or paths.DATA_TICKERS_DIR).resolve()
    use_store = (
        store_path or paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"
    ).resolve()
    use_profile = (
        profile_path
        or paths.OUT_I_CALC_DIR / "ann" / "feature_profiles" / "pruned_inputs.json"
    ).resolve()

    selected_features = _load_selected_feature_names(use_profile)
    feature_matrix = _load_feature_matrix_for_ticker(
        store_path=use_store, ticker=ticker
    )
    if not feature_matrix:
        return []

    out: list[dict[str, Any]] = []
    for date_text in _candidate_anchor_dates(use_rounds):
        rows = build_ann_real_vs_computed_rows(
            selected_date=date_text,
            tickers=[ticker],
            rounds_dir=use_rounds,
            raw_tickers_dir=use_raw,
        )
        if not rows:
            continue
        row = rows[0]
        cls = classify_sgn_case(
            real_sgn=str(row.get("Real SGN") or ""),
            computed_sgn=str(row.get("Computed SGN") or ""),
        )
        if cls is None:
            continue
        feature_payload = dict(feature_matrix.get(date_text) or {})
        if selected_features:
            feature_payload = {
                name: value
                for name, value in feature_payload.items()
                if name in selected_features
            }
        if not feature_payload:
            continue
        out.append(
            {
                "as_of_date": date_text,
                "ticker": str(ticker or "").strip().upper(),
                "class_id": cls,
                "magnitude_label": str(row.get("Computed Magnitude") or ""),
                "features": feature_payload,
            }
        )
    return out


def prepare_sgn_probability_context(
    *,
    ticker: str,
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
    store_path: Path | None = None,
    profile_path: Path | None = None,
    grid_size: int = 35,
    max_features: int = 10,
    k_neighbors: int = 9,
    edge_threshold: float = 0.60,
    rolling_window: int = 20,
) -> dict[str, Any]:
    use_rounds = (rounds_dir or paths.OUT_I_CALC_FOLLOWUP_ML_ROUNDS_DIR).resolve()
    use_raw = (raw_tickers_dir or paths.DATA_TICKERS_DIR).resolve()
    use_store = (
        store_path or paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"
    ).resolve()
    use_profile = (
        profile_path
        or paths.OUT_I_CALC_DIR / "ann" / "feature_profiles" / "pruned_inputs.json"
    ).resolve()

    samples = load_sgn_samples_for_ticker(
        ticker=ticker,
        rounds_dir=use_rounds,
        raw_tickers_dir=use_raw,
        store_path=use_store,
        profile_path=use_profile,
    )
    payload = build_sgn_probability_map_from_samples(
        ticker=ticker,
        samples=samples,
        grid_size=grid_size,
        max_features=max_features,
        k_neighbors=k_neighbors,
        edge_threshold=edge_threshold,
        rolling_window=rolling_window,
    )
    payload["source_sample_count"] = int(len(samples))

    return {
        "ticker": str(ticker or "").strip().upper(),
        "payload": payload,
        "feature_stats": _build_feature_stats(samples),
        "feature_matrix": _load_feature_matrix_for_ticker(
            store_path=use_store,
            ticker=ticker,
        ),
        "selected_features": _load_selected_feature_names(use_profile),
        "k_neighbors": int(k_neighbors),
        "edge_threshold": float(edge_threshold),
    }


def evaluate_sgn_suggestion_from_context(
    *,
    context: dict[str, Any],
    selected_date: str | None,
    computed_sgn: str | None,
) -> dict[str, Any]:
    payload_raw = context.get("payload")
    payload = payload_raw if isinstance(payload_raw, dict) else {}

    selected_payload: dict[str, Any] = {
        "available": False,
        "ticker": str(context.get("ticker") or "").strip().upper(),
        "as_of_date": str(selected_date or "").strip(),
        "reason": "selected_date_unset",
    }
    conditional_payload: dict[str, Any] = {
        "available": False,
        "computed_sgn": "",
        "p_real_pos": 0.0,
        "p_real_neg": 0.0,
        "fallback_used": False,
        "reason": "selected_point_unavailable",
    }
    suggestion_payload: dict[str, Any] = {
        "available": False,
        "value": "N/A",
        "confidence": 0.0,
        "low_confidence": True,
        "reason": "selected_point_unavailable",
    }

    date_text = str(selected_date or "").strip()
    points = list(payload.get("points") or [])
    if not date_text:
        return {
            "selected_point": selected_payload,
            "conditional_real_prob": conditional_payload,
            "suggested_real_sgn": suggestion_payload,
        }
    if not points:
        selected_payload["reason"] = "insufficient_training_points"
        return {
            "selected_point": selected_payload,
            "conditional_real_prob": conditional_payload,
            "suggested_real_sgn": suggestion_payload,
        }

    feature_matrix_raw = context.get("feature_matrix")
    feature_matrix = feature_matrix_raw if isinstance(feature_matrix_raw, dict) else {}
    feature_payload = dict(feature_matrix.get(date_text) or {})
    selected_features_raw = context.get("selected_features")
    selected_features = (
        set(selected_features_raw) if isinstance(selected_features_raw, set) else set()
    )
    if selected_features:
        feature_payload = {
            name: value
            for name, value in feature_payload.items()
            if name in selected_features
        }
    if not feature_payload:
        selected_payload["reason"] = "selected_date_missing_features"
        return {
            "selected_point": selected_payload,
            "conditional_real_prob": conditional_payload,
            "suggested_real_sgn": suggestion_payload,
        }

    stats_raw = context.get("feature_stats")
    stats = stats_raw if isinstance(stats_raw, dict) else {}
    norm_selected = _normalize_feature_payload(feature_payload, stats)
    u_value = _axis_value(
        norm_selected, list(payload.get("weights", {}).get("U") or [])
    )
    v_value = _axis_value(
        norm_selected, list(payload.get("weights", {}).get("V") or [])
    )

    class_prob = _knn_probabilities(
        u=float(u_value),
        v=float(v_value),
        points=points,
        k_neighbors=int(context.get("k_neighbors") or 9),
    )
    selected_payload = {
        "available": True,
        "ticker": str(context.get("ticker") or "").strip().upper(),
        "as_of_date": date_text,
        "U": float(u_value),
        "V": float(v_value),
        "computed_sgn": str(computed_sgn or "").strip(),
        "pred_class": _argmax_class(class_prob),
        "max_prob": float(
            max(float(class_prob.get(cls, 0.0)) for cls in SGN_CLASS_ORDER)
        ),
        "reason": "",
    }
    for cls in SGN_CLASS_ORDER:
        selected_payload[f"prob_{cls}"] = float(class_prob.get(cls, 0.0))

    conditional_payload = conditional_real_probabilities(
        computed_sgn=str(computed_sgn or ""),
        class_probabilities=class_prob,
    )
    suggestion_payload = suggested_real_sgn(
        conditional_payload=conditional_payload,
        low_confidence_threshold=float(context.get("edge_threshold") or 0.60),
    )
    return {
        "selected_point": selected_payload,
        "conditional_real_prob": conditional_payload,
        "suggested_real_sgn": suggestion_payload,
    }


def build_sgn_probability_map(
    *,
    ticker: str,
    rounds_dir: Path | None = None,
    raw_tickers_dir: Path | None = None,
    store_path: Path | None = None,
    profile_path: Path | None = None,
    grid_size: int = 35,
    max_features: int = 10,
    k_neighbors: int = 9,
    edge_threshold: float = 0.60,
    rolling_window: int = 20,
    selected_date: str | None = None,
    computed_sgn: str | None = None,
) -> dict[str, Any]:
    samples = load_sgn_samples_for_ticker(
        ticker=ticker,
        rounds_dir=rounds_dir,
        raw_tickers_dir=raw_tickers_dir,
        store_path=store_path,
        profile_path=profile_path,
    )
    payload = build_sgn_probability_map_from_samples(
        ticker=ticker,
        samples=samples,
        grid_size=grid_size,
        max_features=max_features,
        k_neighbors=k_neighbors,
        edge_threshold=edge_threshold,
        rolling_window=rolling_window,
    )
    payload["source_sample_count"] = len(samples)

    selected_payload: dict[str, Any] = {
        "available": False,
        "ticker": str(ticker or "").strip().upper(),
        "as_of_date": str(selected_date or "").strip(),
        "reason": "selected_date_unset",
    }
    conditional_payload: dict[str, Any] = {
        "available": False,
        "computed_sgn": "",
        "p_real_pos": 0.0,
        "p_real_neg": 0.0,
        "fallback_used": False,
        "reason": "selected_point_unavailable",
    }
    suggestion_payload: dict[str, Any] = {
        "available": False,
        "value": "N/A",
        "confidence": 0.0,
        "low_confidence": True,
        "reason": "selected_point_unavailable",
    }

    date_text = str(selected_date or "").strip()
    if date_text and samples and list(payload.get("points") or []):
        selected_features = _load_selected_feature_names(
            (
                profile_path
                or paths.OUT_I_CALC_DIR
                / "ann"
                / "feature_profiles"
                / "pruned_inputs.json"
            ).resolve()
        )
        feature_matrix = _load_feature_matrix_for_ticker(
            store_path=(
                store_path
                or paths.OUT_I_CALC_DIR / "stores" / "ann_input_features.sqlite"
            ).resolve(),
            ticker=ticker,
        )
        feature_payload = dict(feature_matrix.get(date_text) or {})
        if selected_features:
            feature_payload = {
                name: value
                for name, value in feature_payload.items()
                if name in selected_features
            }
        if feature_payload:
            stats = _build_feature_stats(samples)
            norm_selected = _normalize_feature_payload(feature_payload, stats)
            u_value = _axis_value(
                norm_selected, list(payload.get("weights", {}).get("U") or [])
            )
            v_value = _axis_value(
                norm_selected, list(payload.get("weights", {}).get("V") or [])
            )
            class_prob = _knn_probabilities(
                u=float(u_value),
                v=float(v_value),
                points=list(payload.get("points") or []),
                k_neighbors=k_neighbors,
            )
            selected_payload = {
                "available": True,
                "ticker": str(ticker or "").strip().upper(),
                "as_of_date": date_text,
                "U": float(u_value),
                "V": float(v_value),
                "computed_sgn": str(computed_sgn or "").strip(),
                "pred_class": _argmax_class(class_prob),
                "max_prob": float(
                    max(float(class_prob.get(cls, 0.0)) for cls in SGN_CLASS_ORDER)
                ),
                "reason": "",
            }
            for cls in SGN_CLASS_ORDER:
                selected_payload[f"prob_{cls}"] = float(class_prob.get(cls, 0.0))
            conditional_payload = conditional_real_probabilities(
                computed_sgn=str(computed_sgn or ""),
                class_probabilities=class_prob,
            )
            suggestion_payload = suggested_real_sgn(
                conditional_payload=conditional_payload,
                low_confidence_threshold=float(edge_threshold),
            )
        else:
            selected_payload["reason"] = "selected_date_missing_features"
    elif date_text:
        selected_payload["reason"] = "insufficient_training_points"

    payload["selected_point"] = selected_payload
    payload["conditional_real_prob"] = conditional_payload
    payload["suggested_real_sgn"] = suggestion_payload
    return payload


def write_sgn_map_artifacts(
    *, payload: dict[str, Any], output_dir: Path
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    points_path = output_dir / "sgn_map_points.csv"
    grid_path = output_dir / "sgn_map_grid.csv"
    metrics_path = output_dir / "sgn_map_metrics.json"
    weights_path = output_dir / "sgn_map_weights.json"
    meta_path = output_dir / "sgn_map_metadata.json"

    points = list(payload.get("points") or [])
    grid = list(payload.get("grid") or [])
    metrics = dict(payload.get("metrics") or {})
    weights = dict(payload.get("weights") or {})

    if points:
        with points_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(points[0].keys()))
            writer.writeheader()
            for row in points:
                writer.writerow(row)

    if grid:
        with grid_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(grid[0].keys()))
            writer.writeheader()
            for row in grid:
                writer.writerow(row)

    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    weights_path.write_text(json.dumps(weights, indent=2), encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "generated_at_utc": payload.get("generated_at_utc"),
                "ticker": payload.get("ticker"),
                "class_order": payload.get("class_order"),
                "point_count": payload.get("point_count"),
                "contour_thresholds": payload.get("contour_thresholds"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "points_path": str(points_path),
        "grid_path": str(grid_path),
        "metrics_path": str(metrics_path),
        "weights_path": str(weights_path),
        "metadata_path": str(meta_path),
    }


__all__ = [
    "SGN_CLASS_ORDER",
    "SGN_CLASS_LABELS",
    "build_sgn_probability_map",
    "build_sgn_probability_map_from_samples",
    "classify_sgn_case",
    "conditional_real_probabilities",
    "evaluate_sgn_suggestion_from_context",
    "load_sgn_samples_for_ticker",
    "prepare_sgn_probability_context",
    "suggested_real_sgn",
    "write_sgn_map_artifacts",
]
