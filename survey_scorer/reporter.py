from pathlib import Path

import pandas as pd


def _to_df(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=[
        "respondent_id", "instrument_id", "scale_id", "scale_name",
        "raw_score", "level", "label", "interpretation", "calculated_at",
    ])


def export_detail(rows: list, output_dir: Path) -> Path:
    """One row per respondent × scale."""
    df = _to_df(rows)
    path = output_dir / "results_detail.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_summary(rows: list, output_dir: Path) -> Path:
    """Wide format: one row per respondent, columns = instrument_scale (score)."""
    df = _to_df(rows)
    df["column"] = df["instrument_id"] + "_" + df["scale_id"]
    pivot = df.pivot_table(
        index="respondent_id",
        columns="column",
        values="raw_score",
        aggfunc="first",
    ).reset_index()
    pivot.columns.name = None
    path = output_dir / "results_summary.csv"
    pivot.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_group(rows: list, output_dir: Path) -> Path:
    """Group averages per instrument × scale."""
    df = _to_df(rows)
    df["column"] = df["instrument_id"] + "_" + df["scale_id"]
    group = (
        df.groupby(["instrument_id", "scale_id", "scale_name", "column"])["raw_score"]
        .agg(n="count", mean="mean", min="min", max="max", std="std")
        .round(2)
        .reset_index()
    )
    path = output_dir / "results_group.csv"
    group.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_all(rows: list, output_dir: Path) -> tuple:
    output_dir.mkdir(parents=True, exist_ok=True)
    p1 = export_detail(rows, output_dir)
    p2 = export_summary(rows, output_dir)
    p3 = export_group(rows, output_dir)
    return p1, p2, p3
