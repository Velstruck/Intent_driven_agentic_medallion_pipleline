"""CLI orchestrator with terminal HITL approval gates."""
import argparse
import sys
import uuid
import pandas as pd
from tabulate import tabulate
from agents import profiler, sttm_generator, bronze_agent, silver_agent, gold_agent, reporter
from core.config import ensure_dirs
from core.state import PipelineState


def hitl_gate(layer: str, path: str) -> bool:
    frame = pd.read_csv(path)
    print(f"\n== {layer} STTM ({len(frame)} rules) ==")
    print(tabulate(frame, headers="keys", tablefmt="rounded_outline", showindex=False))
    while True:
        choice = input(f"[{layer}] Approve? [y]es / [n]o abort > ").strip().lower()
        if choice == "y":
            return True
        if choice == "n":
            return False
        print("Please enter y or n.")


def run_pipeline(files: list[str], intent: str) -> PipelineState:
    ensure_dirs()
    state = PipelineState(str(uuid.uuid4()), files, intent)
    state.profile_path = profiler.profile(files, state.run_id)
    state.bronze_sttm_path = sttm_generator.generate_bronze_sttm(state.profile_path, intent, state.run_id)
    if not hitl_gate("Bronze", state.bronze_sttm_path):
        return state
    state.bronze_paths = bronze_agent.run(files, state.bronze_sttm_path, state.run_id)
    state.silver_sttm_path = sttm_generator.generate_silver_sttm(state.bronze_paths, state.bronze_sttm_path, intent, state.run_id)
    if not hitl_gate("Silver", state.silver_sttm_path):
        return state
    state.silver_paths = silver_agent.run(state.bronze_paths, state.silver_sttm_path, state.run_id)
    state.gold_sttm_path = sttm_generator.generate_gold_sttm(state.silver_paths, state.silver_sttm_path, intent, state.run_id)
    if not hitl_gate("Gold", state.gold_sttm_path):
        return state
    state.gold_paths = gold_agent.run(state.silver_paths, state.gold_sttm_path, intent, state.run_id)
    state.report_path = reporter.generate_report(state.gold_paths, intent, state.run_id)
    print(f"\nPipeline complete. Report: {state.report_path}")
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+")
    parser.add_argument("--intent")
    args = parser.parse_args()
    files = args.files or input("Enter CSV file paths: ").split()
    intent = args.intent or input("Enter business intent: ").strip()
    if not files or not intent:
        print("Error: both files and intent are required.")
        sys.exit(1)
    run_pipeline(files, intent)


if __name__ == "__main__":
    main()
