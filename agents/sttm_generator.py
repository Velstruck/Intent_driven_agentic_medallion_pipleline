"""Generate and validate Source-to-Target Mapping CSVs."""
import csv
import io
import json
import re
from pathlib import Path
import pandas as pd
from core.audit import AuditLogger
from core.config import STTM_DIR
from core.llm import call_llm

REQUIRED_COLUMNS = ["source_schema", "source_table", "source_column", "target_schema", "target_table", "target_column", "transformation_type", "transformation_logic"]


def _extract_csv(text: str) -> str:
    match = re.search(r"```(?:csv)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if REQUIRED_COLUMNS[0] in line and REQUIRED_COLUMNS[-1] in line:
            return "\n".join(lines[index:]).strip()
    return text.strip()


def _validate_and_save(csv_text: str, output: Path, raw: str) -> None:
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        raise ValueError("Empty STTM response")
    header = [item.strip() for item in rows[0]]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        output.with_suffix(".raw_llm_response.txt").write_text(raw or csv_text, encoding="utf-8")
        raise ValueError(f"STTM missing required columns: {missing}")
    width = len(header)
    repaired = []
    for row in rows[1:]:
        if len(row) >= width:
            repaired.append(row[: width - 1] + [", ".join(row[width - 1:])])
        elif row:
            repaired.append(row + [""] * (width - len(row)))
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(repaired)


def _save(prompt: str, layer: str, run_id: str) -> str:
    text = call_llm(prompt, max_tokens=5500 if layer == "gold" else 3000, reasoning_effort="medium" if layer == "gold" else "low")
    output = STTM_DIR / f"sttm_{layer}_{run_id[:8]}.csv"
    _validate_and_save(_extract_csv(text), output, text)
    AuditLogger(run_id).log("sttm_generator", f"{layer}_sttm_generated", output_path=str(output))
    return str(output)


def generate_bronze_sttm(profile_path: str, business_intent: str, run_id: str) -> str:
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    prompt = f"Business intent: {business_intent}\nProfile:\n{json.dumps(profile, indent=2)}\nGenerate a CSV with the exact columns {REQUIRED_COLUMNS}. Add type_cast for every source column and metadata_inject rows for _load_timestamp and _source_file per table. Respond only with a csv fenced block."
    return _save(prompt, "bronze", run_id)


def _schemas(paths: list[str]) -> str:
    return "\n".join(f"{Path(path).stem}: {list(pd.read_parquet(path).columns)}" for path in paths)


def generate_silver_sttm(bronze_paths: list[str], bronze_sttm_path: str, business_intent: str, run_id: str) -> str:
    prompt = f"Business intent: {business_intent}\nBronze schemas:\n{_schemas(bronze_paths)}\nGenerate a CSV with the exact columns {REQUIRED_COLUMNS}. Use null_handler, standardize_date, normalize_category, normalize_segment, dedup, surrogate_key, or passthrough rules. Respond only with a csv fenced block."
    return _save(prompt, "silver", run_id)


def generate_gold_sttm(silver_paths: list[str], silver_sttm_path: str, business_intent: str, run_id: str) -> str:
    prompt = f"Business intent: {business_intent}\nSilver schemas:\n{_schemas(silver_paths)}\nGenerate a CSV with the exact columns {REQUIRED_COLUMNS}. Encode concrete join, time_filter, group_by, aggregate, and rank_limit rules using actual table and column names. Respond only with a csv fenced block."
    return _save(prompt, "gold", run_id)
