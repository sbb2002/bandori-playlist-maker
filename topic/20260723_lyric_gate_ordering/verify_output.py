#!/usr/bin/env python
"""Verify and display generated queries output."""
import pandas as pd

csv_path = "out/generated_queries.csv"
df = pd.read_csv(csv_path, encoding='utf-8-sig')

print("=" * 70)
print("GENERATED QUERIES - VERIFICATION")
print("=" * 70)

print("\n=== Sample Queries (First 10) ===\n")
for i in range(min(10, len(df))):
    row = df.iloc[i]
    print(f"{row['query_id']} [{row['category']}]:")
    print(f"  {row['text']}")

print("\n" + "=" * 70)
print("=== Statistics by Category ===")
print("=" * 70 + "\n")

categories = ["band_specified", "intensity_brightness", "situational_functional", "progressive_arc"]
for cat in categories:
    count = len(df[df['category'] == cat])
    target = 150
    status = "✓" if count >= target else "⚠"
    print(f"{status} {cat:30s} : {count:3d}/{target}")

print("\n" + "-" * 70)
total = len(df)
print(f"Total queries: {total}\n")

# Show any categories with low counts
low_cats = [cat for cat in categories if len(df[df['category'] == cat]) < 150]
if low_cats:
    print("⚠ Categories with <150 queries:")
    for cat in low_cats:
        short = len(df[df['category'] == cat])
        print(f"  - {cat}: {short}/150 (need {150-short} more)")
    print("\nRun '01_generate_queries.py' again to continue generation.")
