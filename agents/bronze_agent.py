"""Bronze fidelity layer: type casting where possible, no business logic."""
import re
from datetime import datetime, timezone
from pathlib import Path
import duckdb
import pandas as pd
from core.audit import AuditLogger
from core.config import BRONZE_DIR
from core.llm import call_llm
from core.parquet_safety import sanitize_for_parquet


def _extract_sql(text: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def run(input_files: list[str], sttm_path: str, run_id: str) -> list[str]:
    rules = pd.read_csv(sttm_path)
    outputs = []
    for file_path in input_files:
        table = Path(file_path).stem
        frame = None
        sql_used = "FALLBACK: pd.read_csv passthrough"
        try:
            prompt = f"File: {file_path}\nTable: {table}\nRules:\n{rules[rules.source_table == table].to_string(index=False)}\nReturn one DuckDB SELECT using read_csv_auto('{file_path}', all_varchar=true), TRY_CAST type casts, and no metadata columns."
            sql = _extract_sql(call_llm(prompt, max_tokens=1500))
            if sql:
                frame = duckdb.connect().execute(sql).df()
                sql_used = sql
        except Exception:
            frame = None
        if frame is None:
            frame = pd.read_csv(file_path)
        frame["_load_timestamp"] = datetime.now(timezone.utc).isoformat()
        frame["_source_file"] = str(file_path)
        output = BRONZE_DIR / f"{table}_bronze_{run_id[:8]}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        sanitize_for_parquet(frame).to_parquet(output, index=False)
        outputs.append(str(output))
        AuditLogger(run_id).log("bronze_agent", "table_processed", table=table, output_path=str(output), row_count=len(frame), sql=sql_used)
    return outputs
