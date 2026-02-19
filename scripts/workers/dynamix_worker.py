from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


PROTOCOL_VERSION = 1


def _eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def _emit_payload(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _to_bool_int(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_repo_path(arg_path: str) -> Path:
    def _is_repo(p: Path) -> bool:
        try:
            return p.exists() and (p / "src" / "model" / "forecaster.py").exists()
        except Exception:
            return False

    def _scan_candidates(root: Path) -> Optional[Path]:
        roots = [root, root / "vendor", root.parent]
        for rr in roots:
            if not rr.exists() or not rr.is_dir():
                continue
            try:
                for child in rr.iterdir():
                    if (
                        child.is_dir()
                        and "dynamix" in child.name.lower()
                        and _is_repo(child)
                    ):
                        return child.resolve()
            except Exception:
                continue
        return None

    if arg_path.strip():
        p = Path(arg_path).resolve()
        if _is_repo(p):
            return p
        _eprint(f"DynaMix worker: --dynamix-repo not usable ({p}). Trying fallbacks...")

    env_path = os.environ.get("FIN_DYNAMIX_REPO", "").strip()
    if env_path:
        ep = Path(env_path).resolve()
        if _is_repo(ep):
            return ep
        _eprint(
            f"DynaMix worker: FIN_DYNAMIX_REPO not usable ({ep}). Trying defaults..."
        )

    root = _resolve_repo_root()
    vendor_default = (root / "vendor" / "DynaMix-python").resolve()
    if _is_repo(vendor_default):
        return vendor_default

    repo_default = (root / "DynaMix-python").resolve()
    if _is_repo(repo_default):
        return repo_default

    scanned = _scan_candidates(root)
    if scanned is not None:
        return scanned

    return vendor_default


def _prepare_context(
    context_csv: Path,
    target_col: str,
    context_steps: int,
) -> Tuple[Any, Any, Any]:
    import numpy as np
    import pandas as pd

    df = pd.read_csv(context_csv)
    if df.empty:
        raise ValueError("Context CSV is empty.")

    date_col = "Date" if "Date" in df.columns else str(df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Context index is not DatetimeIndex after parsing.")

    if target_col not in df.columns:
        numeric_candidates = [c for c in df.columns if c != date_col]
        if not numeric_candidates:
            raise ValueError(
                f"Target column '{target_col}' missing and no fallback columns found."
            )
        target_col = numeric_candidates[0]

    y = pd.to_numeric(df[target_col], errors="coerce").dropna()
    if y.empty:
        raise ValueError(f"Target column '{target_col}' has no numeric values.")

    y = y.asfreq("B").ffill().dropna()
    if len(y) < 2:
        raise ValueError("Context series has fewer than 2 rows after cleaning.")

    if context_steps > 0 and len(y) > context_steps:
        y = y.iloc[-context_steps:]

    arr = y.to_numpy(dtype=np.float32).reshape(-1, 1)
    return arr, y.index, target_col


def _auto_select_model(n_dims: int) -> str:
    if n_dims <= 1:
        return "dynamix-3d-alrnn-v1.0"
    if n_dims <= 3:
        return "dynamix-3d-lstm-v1.0"
    return "dynamix-3d-gru-v1.0"


def _run_dynamix_forecast(
    *,
    context_array: Any,
    context_index: Any,
    fh: int,
    model_name: Optional[str],
    standardize: bool,
    fit_nonstationary: bool,
    preprocessing_method: str,
    repo_path: Path,
) -> Tuple[Any, str]:
    import numpy as np
    import pandas as pd

    os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch

    if str(repo_path) not in sys.path:
        sys.path.insert(0, str(repo_path))

    from src.model.forecaster import DynaMixForecaster  # type: ignore
    from src.utilities.utilities import load_hf_model  # type: ignore

    model_id = (
        str(model_name).strip()
        if model_name
        else _auto_select_model(int(context_array.shape[1]))
    )

    device = torch.device("cpu")
    model = load_hf_model(model_id)
    model = model.to(device)
    model.eval()

    context_tensor = torch.tensor(context_array, dtype=torch.float32, device=device)
    forecaster = DynaMixForecaster(model)

    with torch.no_grad():
        forecast_tensor = forecaster.forecast(
            context=context_tensor,
            horizon=int(fh),
            preprocessing_method=str(preprocessing_method),
            standardize=bool(standardize),
            fit_nonstationary=bool(fit_nonstationary),
        )

    forecast_array = np.asarray(forecast_tensor.detach().cpu().numpy(), dtype=float)
    if forecast_array.ndim == 1:
        forecast_array = forecast_array.reshape(-1, 1)

    if len(forecast_array) < int(fh):
        raise RuntimeError(
            f"DynaMix forecast length {len(forecast_array)} is smaller than requested FH={fh}."
        )

    last_date = pd.Timestamp(context_index.max())
    future_index = pd.date_range(
        start=last_date + pd.offsets.BDay(1), periods=int(fh), freq="B"
    )

    out_df = pd.DataFrame(
        {
            "Date": future_index,
            "DYNAMIX_Pred": forecast_array[: int(fh), 0],
            "DYNAMIX_Lower": np.nan,
            "DYNAMIX_Upper": np.nan,
        }
    )

    return out_df, model_id


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dynamix_worker.py",
        description="FIN DynaMix worker (CPU-only) emitting JSON protocol on stdout.",
    )
    parser.add_argument("--ticker", default="UNKNOWN")
    parser.add_argument("--context-csv", required=True)
    parser.add_argument("--target-col", default="Close")
    parser.add_argument("--fh", required=True, type=int)
    parser.add_argument("--artifact-csv", required=True)
    parser.add_argument("--dynamix-repo", default="")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--context-steps", default=2048, type=int)
    parser.add_argument("--preprocessing-method", default="pos_embedding")
    parser.add_argument("--standardize", default="1")
    parser.add_argument("--fit-nonstationary", default="0")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    payload: Dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "ok": False,
        "artifact_csv": None,
        "meta": {
            "ticker": str(args.ticker),
            "device": "cpu",
        },
        "error": None,
    }

    try:
        repo_path = _resolve_repo_path(str(args.dynamix_repo))
        if not repo_path.exists():
            raise FileNotFoundError(
                "DynaMix repository path not found: "
                f"{repo_path}. Set FIN_DYNAMIX_REPO to your DynaMix-python clone."
            )

        context_csv = Path(str(args.context_csv)).resolve()
        if not context_csv.exists():
            raise FileNotFoundError(f"Context CSV not found: {context_csv}")

        context_array, context_index, resolved_target = _prepare_context(
            context_csv=context_csv,
            target_col=str(args.target_col),
            context_steps=max(1, int(args.context_steps)),
        )

        out_df, used_model = _run_dynamix_forecast(
            context_array=context_array,
            context_index=context_index,
            fh=int(args.fh),
            model_name=str(args.model_name).strip() or None,
            standardize=_to_bool_int(str(args.standardize)),
            fit_nonstationary=_to_bool_int(str(args.fit_nonstationary)),
            preprocessing_method=str(args.preprocessing_method),
            repo_path=repo_path,
        )

        artifact_csv = Path(str(args.artifact_csv)).resolve()
        artifact_csv.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(artifact_csv, index=False, date_format="%Y-%m-%d")

        payload["ok"] = True
        payload["artifact_csv"] = str(artifact_csv)
        payload["meta"] = {
            "ticker": str(args.ticker),
            "device": "cpu",
            "rows": int(len(out_df)),
            "columns": list(out_df.columns),
            "model_name": used_model,
            "target_col": resolved_target,
        }
        _emit_payload(payload)
        return 0

    except Exception as e:
        _eprint(f"DynaMix worker failure: {type(e).__name__}: {e}")
        _eprint(traceback.format_exc())
        payload["error"] = {
            "type": type(e).__name__,
            "message": str(e),
        }
        _emit_payload(payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
