"""Generate an HTML report from Gold Parquet output."""
import html
import json
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from core.audit import AuditLogger
from core.config import REPORTS_DIR
from core.llm import call_llm


def generate_report(gold_paths: list[str], business_intent: str, run_id: str) -> str:
    frame = pd.read_parquet(gold_paths[0])
    narrative = "Report generated from the Gold analytics layer."
    try:
        prompt = f"Business intent: {business_intent}\nColumns: {list(frame.columns)}\nPreview:\n{frame.head(10).to_string(index=False)}\nWrite a concise executive summary."
        narrative = call_llm(prompt, max_tokens=1200).strip()
    except Exception:
        pass
    table = frame.to_html(index=False, classes="data-table", border=0, na_rep="---")
    chart_html = "<p>No chartable numeric result was produced.</p>"
    numeric = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    categories = [column for column in frame.columns if column not in numeric]
    if numeric and categories and not frame.empty:
        figure = go.Figure(go.Bar(x=frame[categories[0]].astype(str).tolist(), y=frame[numeric[0]].astype(float).tolist()))
        figure.update_layout(title=f"{numeric[0]} by {categories[0]}", template="plotly_white")
        chart_html = figure.to_html(full_html=False, include_plotlyjs="cdn")
    body = f"""<!doctype html><html><head><meta charset='utf-8'><title>IDAMP Report</title><style>body{{font-family:Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#1a1a2e}}h1{{color:#1565c0;border-bottom:2px solid #1565c0;padding-bottom:8px}}h2{{color:#1565c0;margin-top:32px}}.narrative{{background:#f0f5ff;border-left:4px solid #1565c0;padding:16px;white-space:pre-wrap;line-height:1.6}}.data-table{{border-collapse:collapse;width:100%;font-size:13px}}.data-table th{{background:#1565c0;color:white;padding:8px;text-align:left}}.data-table td{{padding:7px;border-bottom:1px solid #ddd}}.data-table tr:nth-child(even){{background:#f5f7fa}}</style></head><body><h1>Business Intelligence Report</h1><p><b>Run ID:</b> {html.escape(run_id)}</p><p><b>Business Intent:</b> {html.escape(business_intent)}</p><h2>Executive Summary</h2><div class='narrative'>{html.escape(narrative)}</div><h2>Data Results</h2>{table}<h2>Visual Analysis</h2>{chart_html}</body></html>"""
    output = REPORTS_DIR / f"report_{run_id[:8]}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    AuditLogger(run_id).log("reporter", "report_generated", output_path=str(output))
    return str(output)
