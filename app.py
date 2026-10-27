"""Streamlit UI for the IDAMP pipeline with HITL STTM approval gates."""
import json
import pathlib
import uuid
import pandas as pd
import streamlit as st
from agents import profiler, sttm_generator, bronze_agent, silver_agent, gold_agent, reporter
from core.config import AUDIT_DIR, ensure_dirs, UPLOADS_DIR
from core.state import PipelineState

st.set_page_config(page_title="IDAMP - Agentic Medallion Pipeline", page_icon="IDAMP", layout="wide")

STAGES = ["input", "running_phase1", "bronze_hitl", "running_phase2", "silver_hitl", "running_phase3", "gold_hitl", "running_phase4", "complete"]
for key, value in {"stage": "input", "state": None, "intent": "", "input_files": [], "report_html": ""}.items():
    st.session_state.setdefault(key, value)


def sidebar() -> None:
    st.sidebar.title("Pipeline Status")
    current = st.session_state.stage
    for stage in STAGES:
        marker = "[done]" if STAGES.index(stage) < STAGES.index(current) else "[now]" if stage == current else "[ ]"
        st.sidebar.write(f"{marker} {stage.replace('_', ' ').title()}")
    if st.session_state.get("run_id"):
        st.sidebar.code(st.session_state.run_id[:8])


def run_step(label, function) -> None:
    with st.spinner(label):
        try:
            function()
        except Exception as error:
            st.error(f"Pipeline step failed: {error}")
            st.stop()


sidebar()
st.title("Intent-Driven Agentic Medallion Pipeline")

if st.session_state.stage == "input":
    uploads = st.file_uploader("Upload raw CSV files", type="csv", accept_multiple_files=True)
    intent = st.text_area("Business Question / Intent", placeholder="Top 5 revenue-generating products in the last 4 quarters?")
    if st.button("Start Pipeline", type="primary", disabled=not uploads or not intent):
        ensure_dirs()
        paths = []
        for upload in uploads:
            destination = UPLOADS_DIR / upload.name
            destination.write_bytes(upload.getbuffer())
            paths.append(str(destination))
        st.session_state.input_files = paths
        st.session_state.intent = intent.strip()
        st.session_state.run_id = str(uuid.uuid4())
        st.session_state.stage = "running_phase1"
        st.rerun()

elif st.session_state.stage == "running_phase1":
    state = PipelineState(st.session_state.run_id, st.session_state.input_files, st.session_state.intent)
    run_step("Profiling and generating Bronze STTM", lambda: (setattr(state, "profile_path", profiler.profile(state.input_files, state.run_id)), setattr(state, "bronze_sttm_path", sttm_generator.generate_bronze_sttm(state.profile_path, state.business_intent, state.run_id))))
    st.session_state.state = state
    st.session_state.stage = "bronze_hitl"
    st.rerun()

elif st.session_state.stage in {"bronze_hitl", "silver_hitl", "gold_hitl"}:
    state = st.session_state.state
    layer = st.session_state.stage.split("_")[0]
    path = getattr(state, f"{layer}_sttm_path")
    edited = st.data_editor(pd.read_csv(path), use_container_width=True, num_rows="dynamic", key=f"{layer}_editor")
    approve, regenerate, abort = st.columns(3)
    if approve.button("Approve and Continue", type="primary"):
        edited.to_csv(path, index=False)
        state.stage = layer
        st.session_state.stage = {"bronze": "running_phase2", "silver": "running_phase3", "gold": "running_phase4"}[layer]
        st.rerun()
    if regenerate.button("Regenerate"):
        if layer == "bronze":
            state.bronze_sttm_path = sttm_generator.generate_bronze_sttm(state.profile_path, state.business_intent, state.run_id)
        elif layer == "silver":
            state.silver_sttm_path = sttm_generator.generate_silver_sttm(state.bronze_paths, state.bronze_sttm_path, state.business_intent, state.run_id)
        else:
            state.gold_sttm_path = sttm_generator.generate_gold_sttm(state.silver_paths, state.silver_sttm_path, state.business_intent, state.run_id)
        st.session_state.state = state
        st.rerun()
    if abort.button("Abort"):
        st.session_state.stage = "aborted"
        st.rerun()

elif st.session_state.stage == "running_phase2":
    state = st.session_state.state
    run_step("Running Bronze and generating Silver STTM", lambda: (setattr(state, "bronze_paths", bronze_agent.run(state.input_files, state.bronze_sttm_path, state.run_id)), setattr(state, "silver_sttm_path", sttm_generator.generate_silver_sttm(state.bronze_paths, state.bronze_sttm_path, state.business_intent, state.run_id))))
    st.session_state.stage = "silver_hitl"
    st.rerun()

elif st.session_state.stage == "running_phase3":
    state = st.session_state.state
    run_step("Running Silver and generating Gold STTM", lambda: (setattr(state, "silver_paths", silver_agent.run(state.bronze_paths, state.silver_sttm_path, state.run_id)), setattr(state, "gold_sttm_path", sttm_generator.generate_gold_sttm(state.silver_paths, state.silver_sttm_path, state.business_intent, state.run_id))))
    st.session_state.stage = "gold_hitl"
    st.rerun()

elif st.session_state.stage == "running_phase4":
    state = st.session_state.state
    run_step("Running Gold and generating report", lambda: (setattr(state, "gold_paths", gold_agent.run(state.silver_paths, state.gold_sttm_path, state.business_intent, state.run_id)), setattr(state, "report_path", reporter.generate_report(state.gold_paths, state.business_intent, state.run_id))))
    st.session_state.report_html = pathlib.Path(state.report_path).read_text(encoding="utf-8")
    st.session_state.stage = "complete"
    st.rerun()

elif st.session_state.stage == "complete":
    state = st.session_state.state
    report, gold, sttms, audit = st.tabs(["Report", "Gold Data", "All STTMs", "Audit Log"])
    with report:
        st.components.v1.html(st.session_state.report_html, height=800, scrolling=True)
        st.download_button("Download HTML Report", st.session_state.report_html, f"report_{state.run_id[:8]}.html", "text/html")
    with gold:
        for path in state.gold_paths:
            st.dataframe(pd.read_parquet(path), use_container_width=True)
    with sttms:
        for path in (state.bronze_sttm_path, state.silver_sttm_path, state.gold_sttm_path):
            st.dataframe(pd.read_csv(path), use_container_width=True)
    with audit:
        path = AUDIT_DIR / f"{state.run_id}.jsonl"
        if path.exists():
            st.dataframe(pd.DataFrame(json.loads(line) for line in path.read_text().splitlines()))
    if st.button("Start a New Run"):
        st.session_state.clear()
        st.rerun()

elif st.session_state.stage == "aborted":
    st.error("Pipeline aborted at a human approval gate.")
