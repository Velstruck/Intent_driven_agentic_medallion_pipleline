"""Deterministic CSV profiler with optional LLM interpretation."""
import json
import re
from pathlib import Path
import pandas as pd
from core.audit import AuditLogger
from core.config import PROFILES_DIR
from core.llm import call_llm

DATE_RE = re.compile(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{4}$|^\d{4}-\d{2}-\d{2}$")


def _profile_column(series: pd.Series) -> dict:
    non_null = series.dropna()
    info = {"dtype": str(series.dtype), "null_count": int(series.isna().sum()), "null_pct": round(float(series.isna().mean() * 100), 2), "unique_count": int(series.nunique(dropna=True)), "sample_values": [str(value) for value in non_null.unique()[:5]]}
    if pd.api.types.is_numeric_dtype(series) and not non_null.empty:
        info.update(min=float(non_null.min()), max=float(non_null.max()), mean=round(float(non_null.mean()), 4))
    flags = []
    if series.dtype == object and not non_null.empty:
        values = non_null.astype(str)
        if values.map(lambda value: bool(DATE_RE.match(value))).mean() > 0.1:
            flags.append("date_like")
        if values.str.len().mean() < 6:
            flags.append("possible_abbreviations")
    info["quality_flags"] = flags
    return info


def profile(file_paths: list[str], run_id: str) -> str:
    tables = {}
    for file_path in file_paths:
        frame = pd.read_csv(file_path, low_memory=False)
        tables[Path(file_path).stem] = {"row_count": len(frame), "columns": {column: _profile_column(frame[column]) for column in frame.columns}}
    join_keys = {}
    for table, info in tables.items():
        for column in info["columns"]:
            if column.endswith("_id"):
                join_keys.setdefault(column, []).append(table)
    join_keys = {key: value for key, value in join_keys.items() if len(value) > 1}
    try:
        prompt = "Profile summary:\n" + json.dumps({"tables": tables, "candidate_join_keys": join_keys}, indent=2) + "\nReturn JSON with quality_summary, critical_issues, transformation_recommendations, join_key_reasoning."
        analysis = json.loads(re.search(r"```json\s*(.*?)```", call_llm(prompt, max_tokens=1500), re.DOTALL).group(1))
    except Exception as error:
        analysis = {"quality_summary": "Rule-based only (LLM unavailable)", "critical_issues": [], "transformation_recommendations": {}, "join_key_reasoning": f"LLM call failed: {error}"}
    output = PROFILES_DIR / f"profile_combined_{run_id[:8]}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"run_id": run_id, "tables": tables, "candidate_join_keys": join_keys, "llm_analysis": analysis}, indent=2), encoding="utf-8")
    AuditLogger(run_id).log("profiler", "profile_generated", output_path=str(output))
    return str(output)
