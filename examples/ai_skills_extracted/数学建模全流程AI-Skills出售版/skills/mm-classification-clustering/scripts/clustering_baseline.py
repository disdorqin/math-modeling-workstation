"""Run KMeans or DBSCAN clustering baselines with PCA visualization."""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def parse_cols(value):
    return [x.strip() for x in value.split(",") if x.strip()] if value else []


def run(input_path, output_dir, columns_arg, method, clusters, eps, min_samples):
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    df = pd.read_csv(p)
    cols = parse_cols(columns_arg) or list(df.select_dtypes(include="number").columns)
    if len(cols) < 2:
        raise ValueError("at least two numeric feature columns are required")
    X = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(X) < 3:
        raise ValueError("at least three complete rows are required")
    Xs = StandardScaler().fit_transform(X)
    if method == "kmeans":
        labels = KMeans(n_clusters=clusters, random_state=42, n_init=10).fit_predict(Xs)
    else:
        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(Xs)
    sil = None
    if len(set(labels)) > 1 and len(set(labels)) < len(labels):
        sil = float(silhouette_score(Xs, labels))
    coords = PCA(n_components=2, random_state=42).fit_transform(Xs)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = X.copy()
    result["cluster"] = labels
    result.to_csv(output / "cluster_assignments.csv", index=False)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(coords[:, 0], coords[:, 1], c=labels, cmap="tab10")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    fig.tight_layout()
    fig.savefig(output / "cluster_pca.png", dpi=150)
    plt.close(fig)
    (output / "summary.md").write_text(f"# Clustering Baseline\n\n- Method: {method}\n- Silhouette: {sil}\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run clustering baseline.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--columns")
    parser.add_argument("--method", choices=["kmeans", "dbscan"], default="kmeans")
    parser.add_argument("--clusters", type=int, default=3)
    parser.add_argument("--eps", type=float, default=0.5)
    parser.add_argument("--min-samples", type=int, default=3)
    args = parser.parse_args()
    try:
        return run(args.input, args.output, args.columns, args.method, args.clusters, args.eps, args.min_samples)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
