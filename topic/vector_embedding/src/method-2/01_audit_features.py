"""Stage 0: Audit acoustic features against ground truth labels (DESIGN.md §1a).

Reproduces the data quality check from 2026-07-17 that identified energy_proxy and
energy_full as the only viable intensity candidates.

Output:
  - out/feature_audit.csv: dimension, label, n, mean_energy, mean_energy_proxy,
    mean_energy_full, mean_i_mean
"""
import sys
from pathlib import Path

import pandas as pd

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def audit_features():
    """Audit acoustic features against ground truth labels."""
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    df_master = pd.read_csv(config.SONGS_MASTER_CSV)
    df_labels = pd.read_csv(config.GROUND_TRUTH_LABELS_CSV)

    # Merge by idx (ground_truth_labels has no tag, only idx and band+song)
    df_labels = df_labels.rename(columns={"idx": "idx"})
    df_joined = df_labels.merge(
        df_master[["idx", "energy", "energy_proxy", "energy_full", "i_mean"]],
        on="idx",
        how="left"
    )

    print("Auditing acoustic features against ground truth labels...")
    print(f"Total labeled rows: {len(df_joined)}")

    # Group by dimension + label and compute means
    results = []
    for (dimension, label), group in df_joined.groupby(["dimension", "label"]):
        n = len(group)
        mean_energy = group["energy"].mean()
        mean_energy_proxy = group["energy_proxy"].mean()
        mean_energy_full = group["energy_full"].mean()
        mean_i_mean = group["i_mean"].mean()

        results.append({
            "dimension": dimension,
            "label": label,
            "n": n,
            "mean_energy": round(mean_energy, 6),
            "mean_energy_proxy": round(mean_energy_proxy, 6),
            "mean_energy_full": round(mean_energy_full, 6),
            "mean_i_mean": round(mean_i_mean, 6),
        })

        print(f"\n{dimension} / {label} (n={n}):")
        print(f"  energy:         {mean_energy:.6f}")
        print(f"  energy_proxy:   {mean_energy_proxy:.6f}")
        print(f"  energy_full:    {mean_energy_full:.6f}")
        print(f"  i_mean:         {mean_i_mean:.6f}")

    df_audit = pd.DataFrame(results)
    audit_csv = config.OUT_DIR / "feature_audit.csv"
    df_audit.to_csv(audit_csv, index=False, encoding="utf-8")
    print(f"\nSaved audit report to {audit_csv}")


if __name__ == "__main__":
    audit_features()
