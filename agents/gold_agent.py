"""Gold analytics layer with LLM SQL and largest-table fallback."""
import re
from pathlib import Path
import duckdb
import pandas as pd
from core.audit import AuditLogger
from core.config import GOLD_DIR
from core.llm import call_llm
from core.parquet_safety import sanitize_for_parquet


def _extract_sql(text: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _fix_table_names(sql: str, names: list[str]) -> str:
    for name in names:
        bare = re.sub(r"_[0-9a-f]{8}$", "", name)
        sql = re.sub(rf"\b{re.escape(bare)}\b", name, sql)
    return sql


def run(silver_paths: list[str], sttm_path: str, business_intent: str, run_id: str) -> list[str]:
    rules = pd.read_csv(sttm_path)
    conn = duckdb.connect()
    names = [Path(path).stem for path in silver_paths]
    for name, path in zip(names, silver_paths):
        conn.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet('{path}')")
    schemas = "\n".join(f"{name}: {list(pd.read_parquet(path).columns)}" for name, path in zip(names, silver_paths))
    frame = None
    sql_used = ""
    try:
        prompt = f"Business intent: {business_intent}\nSchemas:\n{schemas}\nGold STTM:\n{rules.to_string(index=False)}\nReturn one DuckDB SELECT with joins, grouping, aggregate, date filters, order, and limit as required. Cast VARCHAR dates to DATE and do not join on pk_ columns."
        sql = _fix_table_names(_extract_sql(call_llm(prompt, max_tokens=3500, reasoning_effort="medium")), names)
        if sql:
            frame = conn.execute(sql).df()
            sql_used = sql
    except Exception as error:
        failure = GOLD_DIR / f"gold_sql_failure_{run_id[:8]}.txt"
        failure.write_text(str(error), encoding="utf-8")
        AuditLogger(run_id).log("gold_agent", "sql_generation_failed", error=str(error), debug_file=str(failure))
    if frame is None:
        fallback = max(silver_paths, key=lambda path: len(pd.read_parquet(path)))
        frame = pd.read_parquet(fallback)
        sql_used = f"FALLBACK: {fallback}"
    if frame.empty:
        AuditLogger(run_id).log("gold_agent", "sql_returned_zero_rows", sql=sql_used)
    frame.insert(0, "pk_gold_id", range(1, len(frame) + 1))
    output = GOLD_DIR / f"sales_analytics_gold_{run_id[:8]}.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)
    sanitize_for_parquet(frame).to_parquet(output, index=False)
    AuditLogger(run_id).log("gold_agent", "gold_table_generated", output_path=str(output), row_count=len(frame), sql=sql_used)
    return [str(output)]
