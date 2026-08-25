"""Chronological train/val/test split. Never shuffle a time series — a
random split leaks future information into training and inflates accuracy.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MERGED_PATH = ROOT / "data" / "processed" / "merged.parquet"

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
# remainder (0.15) is test


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = len(df)
    train_end = int(n * TRAIN_FRAC)
    val_end = int(n * (TRAIN_FRAC + VAL_FRAC))

    train = df.iloc[:train_end]
    val = df.iloc[train_end:val_end]
    test = df.iloc[val_end:]

    assert train.index.max() < val.index.min()
    assert val.index.max() < test.index.min()

    return train, val, test


def load_splits() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = pd.read_parquet(MERGED_PATH)
    return chronological_split(df)


if __name__ == "__main__":
    train, val, test = load_splits()
    for name, part in [("train", train), ("val", val), ("test", test)]:
        print(f"{name}: {len(part):5d} rows  {part.index.min()} -> {part.index.max()}")
