from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_table(path: Path, sheet_name: str | int | None = 0) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        selected = 0 if sheet_name is None else sheet_name
        return pd.read_excel(path, sheet_name=selected)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported tabular format: {suffix or '<none>'}")

