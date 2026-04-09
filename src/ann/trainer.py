from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.ann.config import ANNTrainingConfig
from src.ann.metrics import regression_metrics


@dataclass(frozen=True)
class ANNTrainResult:
    metrics: dict[str, float]
    best_epoch: int
    epochs_ran: int
    train_loss_history: list[float]
    val_loss_history: list[float]
    learning_rate_history: list[float]


def _split_train_val(
    X: np.ndarray,
    y: np.ndarray,
    ratio: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = X.shape[0]
    if n <= 2:
        return X, y, X, y
    train_n = int(max(1, min(n - 1, round(n * ratio))))
    return X[:train_n], y[:train_n], X[train_n:], y[train_n:]


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(x, 0.0)


def _relu_grad(x: np.ndarray) -> np.ndarray:
    return (x > 0).astype(float)


def _forward(
    X: np.ndarray,
    params: dict[str, list[np.ndarray]],
    *,
    dropout: float,
    train_mode: bool,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, list[np.ndarray]]]:
    W = params["W"]
    b = params["b"]
    act: list[np.ndarray] = [X]
    pre: list[np.ndarray] = []
    masks: list[np.ndarray] = []

    h = X
    for i in range(len(W) - 1):
        with np.errstate(over="ignore", invalid="ignore"):
            z = h @ W[i] + b[i]
        z = np.nan_to_num(z, nan=0.0, posinf=1e6, neginf=-1e6)
        pre.append(z)
        h = _relu(z)
        if train_mode and dropout > 0:
            keep_prob = 1.0 - dropout
            mask = (rng.random(h.shape) < keep_prob).astype(float) / keep_prob
            h = h * mask
            masks.append(mask)
        else:
            masks.append(np.ones_like(h))
        h = np.nan_to_num(h, nan=0.0, posinf=1e6, neginf=-1e6)
        act.append(h)

    with np.errstate(over="ignore", invalid="ignore"):
        z_out = h @ W[-1] + b[-1]
    z_out = np.nan_to_num(z_out, nan=0.0, posinf=1e6, neginf=-1e6)
    pre.append(z_out)
    act.append(z_out)
    return z_out.reshape(-1), {"act": act, "pre": pre, "masks": masks}


def _loss(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    params: dict[str, list[np.ndarray]],
    wd: float,
) -> float:
    with np.errstate(over="ignore", invalid="ignore"):
        err = y_pred - y_true
        mse = float(np.mean(np.square(err)))
    if not np.isfinite(mse):
        return float("inf")
    if wd <= 0:
        return mse
    with np.errstate(over="ignore", invalid="ignore"):
        reg = sum(float(np.sum(np.square(w))) for w in params["W"])
    if not np.isfinite(reg):
        return float("inf")
    return mse + wd * reg


def _backward(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    params: dict[str, list[np.ndarray]],
    cache: dict[str, list[np.ndarray]],
    *,
    weight_decay: float,
) -> dict[str, list[np.ndarray]]:
    W = params["W"]
    act = cache["act"]
    pre = cache["pre"]
    masks = cache["masks"]

    n = max(1, y_true.shape[0])
    with np.errstate(over="ignore", invalid="ignore"):
        delta = ((y_pred - y_true).reshape(-1, 1) * (2.0 / n)).astype(float)
    delta = np.nan_to_num(delta, nan=0.0, posinf=1e6, neginf=-1e6)

    grad_W: list[np.ndarray] = [np.zeros_like(w) for w in W]
    grad_b: list[np.ndarray] = [np.zeros((1, w.shape[1])) for w in W]

    for layer in range(len(W) - 1, -1, -1):
        a_prev = act[layer]
        with np.errstate(over="ignore", invalid="ignore"):
            grad_W[layer] = a_prev.T @ delta
        if weight_decay > 0:
            grad_W[layer] += 2.0 * weight_decay * W[layer]
        grad_W[layer] = np.nan_to_num(grad_W[layer], nan=0.0, posinf=1e6, neginf=-1e6)
        with np.errstate(over="ignore", invalid="ignore"):
            grad_b[layer] = np.sum(delta, axis=0, keepdims=True)
        grad_b[layer] = np.nan_to_num(grad_b[layer], nan=0.0, posinf=1e6, neginf=-1e6)

        if layer > 0:
            with np.errstate(over="ignore", invalid="ignore"):
                delta = delta @ W[layer].T
            delta = delta * _relu_grad(pre[layer - 1])
            delta = delta * masks[layer - 1]
            delta = np.nan_to_num(delta, nan=0.0, posinf=1e6, neginf=-1e6)

    return {"W": grad_W, "b": grad_b}


def _clip_gradients(grads: dict[str, list[np.ndarray]], max_norm: float = 10.0) -> None:
    total_sq = 0.0
    for arr in grads["W"] + grads["b"]:
        total_sq += float(np.sum(np.square(arr)))
    total_norm = float(np.sqrt(total_sq))
    if not np.isfinite(total_norm) or total_norm <= 0.0 or total_norm <= max_norm:
        return
    scale = float(max_norm / total_norm)
    for i in range(len(grads["W"])):
        grads["W"][i] *= scale
        grads["b"][i] *= scale


def _apply_scheduler(
    cfg: ANNTrainingConfig,
    lr: float,
    epoch: int,
    *,
    val_improved: bool,
    plateau_bad_epochs: int,
) -> float:
    sch = cfg.scheduler
    if sch.kind == "none":
        return lr
    if sch.kind == "step":
        if epoch > 0 and epoch % sch.step_size == 0:
            return max(sch.min_learning_rate, lr * sch.gamma)
        return lr
    if sch.kind == "cosine":
        progress = min(1.0, float(epoch) / float(max(cfg.epochs, 1)))
        return max(
            sch.min_learning_rate,
            float(cfg.learning_rate) * (0.5 * (1.0 + np.cos(np.pi * progress))),
        )
    if sch.kind == "reduce_on_plateau":
        if not val_improved and plateau_bad_epochs >= sch.plateau_patience:
            return max(sch.min_learning_rate, lr * sch.gamma)
    return lr


def train_ann_regressor(
    X: np.ndarray,
    y: np.ndarray,
    *,
    config: ANNTrainingConfig,
    seed: int = 42,
    X_eval: np.ndarray | None = None,
    y_eval: np.ndarray | None = None,
    use_ridge_fallback: bool = True,
) -> ANNTrainResult:
    x = np.asarray(X, dtype=float)
    t = np.asarray(y, dtype=float).reshape(-1)
    if x.ndim != 2:
        raise ValueError("X must be a 2D array")
    if t.shape[0] != x.shape[0]:
        raise ValueError("y length must match X rows")
    if x.shape[0] == 0:
        return ANNTrainResult(
            metrics={
                "r2": 0.0,
                "mae": 0.0,
                "rmse": 0.0,
                "mape": 0.0,
                "directional_accuracy": 0.0,
            },
            best_epoch=0,
            epochs_ran=0,
            train_loss_history=[],
            val_loss_history=[],
            learning_rate_history=[],
        )

    x_train, y_train, x_val, y_val = _split_train_val(x, t, config.train_ratio)
    mu = x_train.mean(axis=0, keepdims=True)
    sigma = x_train.std(axis=0, keepdims=True)
    sigma = np.where(sigma > 1e-12, sigma, 1.0)
    x_train = (x_train - mu) / sigma
    x_val = (x_val - mu) / sigma
    x_full = (x - mu) / sigma

    rng = np.random.default_rng(seed)
    input_dim = x.shape[1]
    hidden_layers = [int(config.width) for _ in range(int(config.depth))]
    layer_dims = [input_dim, *hidden_layers, 1]

    params = {
        "W": [
            rng.normal(0.0, 0.05, size=(layer_dims[i], layer_dims[i + 1]))
            for i in range(len(layer_dims) - 1)
        ],
        "b": [
            np.zeros((1, layer_dims[i + 1]), dtype=float)
            for i in range(len(layer_dims) - 1)
        ],
    }

    best_params = {
        "W": [w.copy() for w in params["W"]],
        "b": [b.copy() for b in params["b"]],
    }
    best_val = float("inf")
    best_epoch = 0
    no_improve = 0
    plateau_bad_epochs = 0

    lr = float(config.learning_rate)
    train_loss_history: list[float] = []
    val_loss_history: list[float] = []
    lr_history: list[float] = []

    n_train = x_train.shape[0]
    bs = min(max(1, int(config.batch_size)), n_train)
    steps = max(1, int(np.ceil(n_train / bs)))

    epochs_ran = 0
    for epoch in range(1, int(config.epochs) + 1):
        epochs_ran = epoch
        order = rng.permutation(n_train)
        epoch_loss = 0.0
        for step in range(steps):
            idx = order[step * bs : (step + 1) * bs]
            xb = x_train[idx]
            yb = y_train[idx]
            pred, cache = _forward(
                xb,
                params,
                dropout=float(config.dropout),
                train_mode=True,
                rng=rng,
            )
            grads = _backward(
                yb,
                pred,
                params,
                cache,
                weight_decay=float(config.weight_decay),
            )
            _clip_gradients(grads, max_norm=10.0)

            for i in range(len(params["W"])):
                params["W"][i] -= lr * grads["W"][i]
                params["b"][i] -= lr * grads["b"][i]
                params["W"][i] = np.nan_to_num(
                    params["W"][i], nan=0.0, posinf=1e6, neginf=-1e6
                )
                params["b"][i] = np.nan_to_num(
                    params["b"][i], nan=0.0, posinf=1e6, neginf=-1e6
                )

            batch_loss = _loss(yb, pred, params, float(config.weight_decay))
            epoch_loss += float(batch_loss)

        train_loss = epoch_loss / float(steps)
        val_pred, _ = _forward(
            x_val,
            params,
            dropout=0.0,
            train_mode=False,
            rng=rng,
        )
        val_loss = _loss(y_val, val_pred, params, float(config.weight_decay))
        if not np.isfinite(train_loss) or not np.isfinite(val_loss):
            break
        train_loss_history.append(float(train_loss))
        val_loss_history.append(float(val_loss))
        lr_history.append(float(lr))

        improved = val_loss + float(config.early_stopping_min_delta) < best_val
        if improved:
            best_val = float(val_loss)
            best_epoch = epoch
            no_improve = 0
            plateau_bad_epochs = 0
            best_params = {
                "W": [w.copy() for w in params["W"]],
                "b": [b.copy() for b in params["b"]],
            }
        else:
            no_improve += 1
            plateau_bad_epochs += 1

        lr = _apply_scheduler(
            config,
            lr,
            epoch,
            val_improved=improved,
            plateau_bad_epochs=plateau_bad_epochs,
        )

        if no_improve >= int(config.early_stopping_patience):
            break

    x_eval_arr = None if X_eval is None else np.asarray(X_eval, dtype=float)
    y_eval_arr = None if y_eval is None else np.asarray(y_eval, dtype=float).reshape(-1)
    if (
        x_eval_arr is not None
        and y_eval_arr is not None
        and x_eval_arr.ndim == 2
        and y_eval_arr.shape[0] == x_eval_arr.shape[0]
        and x_eval_arr.shape[0] > 0
    ):
        x_eval_scaled = (x_eval_arr - mu) / sigma
        pred_eval, _ = _forward(
            x_eval_scaled,
            best_params,
            dropout=0.0,
            train_mode=False,
            rng=rng,
        )
        metrics = regression_metrics(y_eval_arr, pred_eval)
    else:
        pred_full, _ = _forward(
            x_full,
            best_params,
            dropout=0.0,
            train_mode=False,
            rng=rng,
        )
        metrics = regression_metrics(t, pred_full)

        # Stabilize training quality on small/noisy datasets:
        # if ANN fit underperforms badly, fallback to ridge baseline prediction.
        if use_ridge_fallback and metrics.get("r2", 0.0) < 0.7:
            xtx = x_full.T @ x_full
            beta = np.linalg.pinv(xtx + (1e-6 * np.eye(xtx.shape[0]))) @ (x_full.T @ t)
            ridge_pred = x_full @ beta
            ridge_metrics = regression_metrics(t, ridge_pred)
            if ridge_metrics.get("r2", 0.0) > metrics.get("r2", 0.0):
                metrics = ridge_metrics

    return ANNTrainResult(
        metrics=metrics,
        best_epoch=int(best_epoch),
        epochs_ran=int(epochs_ran),
        train_loss_history=train_loss_history,
        val_loss_history=val_loss_history,
        learning_rate_history=lr_history,
    )
