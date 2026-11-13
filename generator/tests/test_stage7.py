"""Stage 7 tests: end-to-end pipeline runner, all subcommand, and stage outputs."""
import sys
from pathlib import Path
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "generator"))
sys.path.insert(0, str(REPO_ROOT))

from hst_gen.cli import main  # noqa: E402

CLI_PATH = REPO_ROOT / "generator" / "hst_gen" / "cli.py"


def test_stage7_cli_line_count():
    assert CLI_PATH.exists()
    lines = CLI_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 150, f"generator/hst_gen/cli.py has {len(lines)} lines; must be under 150"


def test_stage7_cli_arguments():
    # Verify that 'all' is accepted with flags
    import argparse
    p = argparse.ArgumentParser(prog="hst_gen")
    p.add_argument("command", choices=["demand", "stage2", "stage3", "stage4", "stage5", "all"])
    p.add_argument("--config", default=None)
    p.add_argument("--out", default="output")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--tickets", type=int, default=None)

    args = p.parse_args(["all", "--out", "test_out", "--tickets", "100000", "--seed", "123", "--config", "custom.yaml"])
    assert args.command == "all"
    assert args.out == "test_out"
    assert args.tickets == 100000
    assert args.seed == 123
    assert args.config == "custom.yaml"


@pytest.fixture(scope="module")
def pipeline_run(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("stage7_e2e")
    main(["all", "--out", str(out_dir), "--tickets", "100000", "--seed", "42"])
    return out_dir


def test_stage7_stage1_outputs(pipeline_run):
    s1_demand = pipeline_run / "stage1_demand.csv"
    s1_summary = pipeline_run / "stage1_summary.md"
    s1_svg = pipeline_run / "stage1_demand.svg"

    assert s1_demand.exists()
    assert s1_summary.exists()
    assert s1_svg.exists()

    df = pd.read_csv(s1_demand)
    assert not df.empty
    assert "tickets" in df.columns
    assert df["tickets"].sum() == 100000


def test_stage7_stage2_outputs(pipeline_run):
    s2 = pipeline_run / "stage2"
    for name in ["employee", "employee_history", "company", "promo", "trip"]:
        f = s2 / f"{name}.csv"
        assert f.exists(), f"Missing Stage 2 file: {f}"
        df = pd.read_csv(f)
        assert not df.empty, f"Stage 2 table {name} is empty"

    assert (s2 / "hidden" / "company_hidden.csv").exists()
    assert (s2 / "stage2_summary.md").exists()


def test_stage7_stage3_outputs(pipeline_run):
    s3 = pipeline_run / "stage3"
    for name in ["ticket_sales", "group_booking", "group_booking_detail", "customer", "refund"]:
        f = s3 / f"{name}.csv"
        assert f.exists(), f"Missing Stage 3 file: {f}"
        df = pd.read_csv(f)
        assert not df.empty, f"Stage 3 table {name} is empty"

    tickets_df = pd.read_csv(s3 / "ticket_sales.csv")
    # Base tickets = 100,000, plus injected ticket anomalies in Stage 5
    assert len(tickets_df) >= 100000

    assert (s3 / "hidden" / "customer_truth.csv").exists()
    assert (s3 / "hidden" / "ticket_group_truth.csv").exists()
    assert (s3 / "stage3_summary.md").exists()


def test_stage7_stage4_outputs(pipeline_run):
    s4 = pipeline_run / "stage4"
    for name in ["fcc_card", "fcc_redemption", "refund", "bank_statement"]:
        f = s4 / f"{name}.csv"
        assert f.exists(), f"Missing Stage 4 file: {f}"
        df = pd.read_csv(f)
        assert not df.empty, f"Stage 4 table {name} is empty"

    assert (s4 / "hidden" / "group_booking_payment.csv").exists()
    assert (s4 / "stage4_summary.md").exists()


def test_stage7_stage5_outputs(pipeline_run):
    s5 = pipeline_run / "stage5"
    anom_file = s5 / "anomaly_label.csv"
    hidden_anom = s5 / "hidden" / "anomaly_label.csv"

    assert anom_file.exists()
    assert hidden_anom.exists()
    assert (s5 / "stage5_summary.md").exists()

    df = pd.read_csv(hidden_anom)
    assert not df.empty
    assert set(df.columns) == {"id", "entity_type", "entity_id", "anomaly_type"}
    assert df["id"].is_unique


def test_stage7_database_table_sources_complete(pipeline_run):
    """Confirm all 17 tables needed by scripts/load_db.py are present and non-empty."""
    from scripts.load_db import TABLE_SOURCES
    for table_name, rel_path in TABLE_SOURCES:
        file_path = pipeline_run / rel_path
        assert file_path.exists(), f"Missing table source {table_name}: {file_path}"
        df = pd.read_csv(file_path)
        assert not df.empty, f"Table source {table_name} is empty"
