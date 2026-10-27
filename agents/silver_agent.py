"""Silver quality layer with SQL attempt and deterministic fallback."""
import re
from pathlib import Path
import duckdb
import pandas as pd
from core.audit import AuditLogger
from core.config import SILVER_DIR
from core.llm import call_llm
from core.parquet_safety import sanitize_for_parquet


def _extract_sql(text: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def run(bronze_paths: list[str], sttm_path: str, run_id: str) -> list[str]:
    rules = pd.read_csv(sttm_path)
    outputs = []
    for path in bronze_paths:
        alias = Path(path).stem
        base = re.sub(rf"_bronze_{run_id[:8]}$", "", alias)
        frame = None
        sql_used = "FALLBACK: read_parquet + drop_duplicates"
        try:
            preview = pd.read_parquet(path).head(200)
            prompt = f"Table: {alias}\nColumns: {list(preview.columns)}\nRules:\n{rules[rules.source_table == base].to_string(index=False)}\nReturn one DuckDB SELECT against {alias} implementing cleansing rules."
            conn = duckdb.connect()
            conn.execute(f"CREATE OR REPLACE TABLE {alias} AS SELECT * FROM read_parquet('{path}')")
            sql = _extract_sql(call_llm(prompt, max_tokens=2500))
            if sql:
                frame = conn.execute(sql).df()
                sql_used = sql
        except Exception:
            frame = None
        if frame is None:
            frame = pd.read_parquet(path).drop_duplicates()
        frame.insert(0, f"pk_{base}_silver_id", range(1, len(frame) + 1))
        output = SILVER_DIR / f"{base}_silver_{run_id[:8]}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        sanitize_for_parquet(frame).to_parquet(output, index=False)
        outputs.append(str(output))
        AuditLogger(run_id).log("silver_agent", "table_processed", table=base, output_path=str(output), row_count=len(frame), sql=sql_used)
    return outputs
