"""Train classification baselines and export metrics plus confusion matrix."""
import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def parse_cols(value):
    return [x.strip() for x in value.split(",") if x.strip()] if value else []


def run(input_path, output_dir, target, features_arg, model_name, test_size, seed):
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    df = pd.read_csv(p)
    if target not in df.columns:
        raise ValueError(f"missing target column: {target}")
    features = parse_cols(features_arg) or [c for c in df.select_dtypes(include="number").columns if c != target]
    if not features:
        raise ValueError("no numeric feature columns available")
    data = df[features + [target]].dropna()
    if len(data) < 6:
        raise ValueError("at least 6 complete rows are required")
    X = data[features].apply(pd.to_numeric, errors="coerce")
    if X.isna().any().any():
        raise ValueError("features must be numeric")
    y = data[target]
    stratify = y if y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=seed, stratify=stratify)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    models = {
        "logistic": LogisticRegression(max_iter=1000),
        "decision_tree": DecisionTreeClassifier(random_state=seed),
        "random_forest": RandomForestClassifier(n_estimators=100, random_state=seed),
        "svm": SVC(),
    }
    model = models[model_name]
    if model_name in {"logistic", "svm"}:
        model.fit(X_train_s, y_train)
        pred = model.predict(X_test_s)
    else:
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
    precision, recall, f1, _ = precision_recall_fscore_support(y_test, pred, average="weighted", zero_division=0)
    metrics = pd.DataFrame([{"model": model_name, "accuracy": accuracy_score(y_test, pred), "precision": precision, "recall": recall, "f1": f1}])
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output / "metrics.csv", index=False)
    labels = sorted(y.unique())
    pd.DataFrame(confusion_matrix(y_test, pred, labels=labels), index=labels, columns=labels).to_csv(output / "confusion_matrix.csv")
    pd.DataFrame({"actual": y_test.to_numpy(), "predicted": pred}).to_csv(output / "predictions.csv", index=False)
    (output / "summary.md").write_text(f"# Classification Baseline\n\n- Model: {model_name}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Train a classification baseline.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--features")
    parser.add_argument("--model", choices=["logistic", "decision_tree", "random_forest", "svm"], default="logistic")
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        return run(args.input, args.output, args.target, args.features, args.model, args.test_size, args.seed)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
