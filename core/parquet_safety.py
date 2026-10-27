"""Coerce unusual object values before Parquet serialization."""
import pandas as pd


def sanitize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in result.columns:
        if result[column].dtype != object:
            continue
        values = result[column].dropna()
        if not values.empty and not isinstance(values.iloc[0], (str, int, float, bool)):
            result[column] = result[column].astype(str)
    return result
