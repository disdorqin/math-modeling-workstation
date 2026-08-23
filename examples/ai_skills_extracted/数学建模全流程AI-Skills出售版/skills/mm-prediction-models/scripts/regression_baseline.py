"""Train simple regression baselines for numeric prediction tasks."""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def parse_features(value):
    return [x.strip() for x in value.split(",") if x.strip()] if value else []


def run(input_path, output_dir, target, features_arg, model_name, test_size, seed):
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    df = pd.read_csv(path)
    if target not in df.columns:
        raise ValueError(f"missing target column: {target}")
    features = parse_features(features_arg) or [c for c in df.select_dtypes(include="number").columns if c != target]
    if not features:
        raise ValueError("no numeric feature columns available")
    for col in features:
        if col not in df.columns:
            raise ValueError(f"missing feature column: {col}")
    data = df[features + [target]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 5:
        raise ValueError("at least 5 complete rows are required")
    X = data[features]
    y = data[target]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=seed)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    models = {
        "linear": LinearRegression(),
        "ridge": Ridge(random_state=seed),
        "lasso": Lasso(random_state=seed, max_iter=10000),
        "random_forest": RandomForestRegressor(n_estimators=100, random_state=seed),
    }
    if model_name not in models:
        raise ValueError(f"unknown model: {model_name}")
    model = models[model_name]
    if model_name == "random_forest":
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
    else:
        model.fit(X_train_s, y_train)
        pred = model.predict(X_test_s)
    rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
    metrics = pd.DataFrame([{"model": model_name, "MAE": mean_absolute_error(y_test, pred), "RMSE": rmse, "R2": r2_score(y_test, pred)}])
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output / "metrics.csv", index=False)
    pd.DataFrame({"actual": y_test.to_numpy(), "predicted": pred}).to_csv(output / "predictions.csv", index=False)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(y_test, pred)
    ax.set_xlabel("Actual")
    ax.set_ylabel("Predicted")
    ax.set_title(model_name)
    fig.tight_layout()
    fig.savefig(output / "actual_vs_predicted.png", dpi=150)
    plt.close(fig)
    (output / "summary.md").write_text(f"# Regression Baseline\n\n- Model: {model_name}\n- Features: {', '.join(features)}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Train a numeric regression baseline.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output directory.")
    parser.add_argument("--target", required=True, help="Target column.")
    parser.add_argument("--features", help="Comma-separated feature columns. Defaults to numeric columns except target.")
    parser.add_argument("--model", choices=["linear", "ridge", "lasso", "random_forest"], default="linear")
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        if not (0 < args.test_size < 1):
            raise ValueError("test-size must be between 0 and 1")
        return run(args.input, args.output, args.target, args.features, args.model, args.test_size, args.seed)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
