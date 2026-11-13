"""Stage 6 tests: database loading configuration, topological ordering, and CLI."""
import importlib.util
from pathlib import Path
import sys
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOAD_DB_PATH = REPO_ROOT / "scripts" / "load_db.py"


@pytest.fixture(scope="module")
def load_db_module():
    spec = importlib.util.spec_from_file_location("load_db", LOAD_DB_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["load_db"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_stage6_script_line_count():
    assert LOAD_DB_PATH.exists()
    lines = LOAD_DB_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 200, f"scripts/load_db.py has {len(lines)} lines; must be under 200"


def test_stage6_ddl_files(load_db_module):
    expected_ddl = [
        "01_oltp.sql",
        "02_oltp_truth.sql",
        "03_reference_data.sql",
        "04_comments.sql",
    ]
    assert load_db_module.DDL_FILES == expected_ddl
    for ddl in load_db_module.DDL_FILES:
        assert (REPO_ROOT / "sql" / ddl).exists(), f"Missing SQL file: {ddl}"


def test_stage6_table_count_and_sources(load_db_module):
    tables = load_db_module.TABLE_SOURCES
    assert len(tables) == 17, f"Expected 17 tables, got {len(tables)}"

    expected_sources = {
        "oltp.employee": Path("stage2") / "employee.csv",
        "oltp.employee_history": Path("stage2") / "employee_history.csv",
        "oltp.company": Path("stage2") / "company.csv",
        "oltp.promo": Path("stage2") / "promo.csv",
        "oltp.trip": Path("stage2") / "trip.csv",
        "oltp.customer": Path("stage3") / "customer.csv",
        "oltp.group_booking": Path("stage3") / "group_booking.csv",
        "oltp.group_booking_detail": Path("stage3") / "group_booking_detail.csv",
        "oltp.ticket_sales": Path("stage3") / "ticket_sales.csv",
        "oltp.fcc_card": Path("stage4") / "fcc_card.csv",
        "oltp.fcc_redemption": Path("stage4") / "fcc_redemption.csv",
        "oltp.refund": Path("stage4") / "refund.csv",
        "oltp.bank_statement": Path("stage4") / "bank_statement.csv",
        "oltp_truth.customer_truth": Path("stage3") / "hidden" / "customer_truth.csv",
        "oltp_truth.ticket_group_truth": Path("stage3") / "hidden" / "ticket_group_truth.csv",
        "oltp_truth.group_booking_payment": Path("stage4") / "hidden" / "group_booking_payment.csv",
        "oltp_truth.anomaly_label": Path("stage5") / "hidden" / "anomaly_label.csv",
    }

    assert [t[0] for t in tables] == list(expected_sources.keys())
    for table_name, rel_path in tables:
        assert expected_sources[table_name] == rel_path


def test_stage6_topological_dependency_order(load_db_module):
    order = [t[0] for t in load_db_module.TABLE_SOURCES]
    indices = {name: idx for idx, name in enumerate(order)}

    # Explicit foreign key dependencies between the 17 loaded tables
    dependencies = {
        "oltp.employee": [],
        "oltp.employee_history": ["oltp.employee"],
        "oltp.company": [],
        "oltp.promo": [],
        "oltp.trip": [],
        "oltp.customer": [],
        "oltp.group_booking": ["oltp.company", "oltp.promo", "oltp.employee"],
        "oltp.group_booking_detail": ["oltp.group_booking"],
        "oltp.ticket_sales": [
            "oltp.customer", "oltp.trip", "oltp.promo",
            "oltp.employee", "oltp.group_booking"
        ],
        "oltp.fcc_card": ["oltp.customer", "oltp.employee"],
        "oltp.fcc_redemption": ["oltp.fcc_card", "oltp.ticket_sales", "oltp.employee"],
        "oltp.refund": ["oltp.ticket_sales", "oltp.employee"],
        "oltp.bank_statement": [],
        "oltp_truth.customer_truth": ["oltp.customer"],
        "oltp_truth.ticket_group_truth": ["oltp.ticket_sales", "oltp.group_booking"],
        "oltp_truth.group_booking_payment": ["oltp.bank_statement", "oltp.group_booking"],
        "oltp_truth.anomaly_label": [],
    }

    for table, deps in dependencies.items():
        assert table in indices, f"Table {table} missing from order"
        table_idx = indices[table]
        for dep in deps:
            assert dep in indices, f"Dependency {dep} missing from order"
            dep_idx = indices[dep]
            assert dep_idx < table_idx, (
                f"Dependency violation: {dep} (index {dep_idx}) must precede {table} (index {table_idx})"
            )


def test_stage6_cli_argument_parsing(load_db_module):
    # Default options
    default_args = load_db_module.parse_args([])
    assert default_args.host == "localhost"
    assert default_args.port == 5432
    assert default_args.user == "postgres"
    assert default_args.db == "postgres"
    assert default_args.data_dir == "output"
    assert default_args.skip_checks is False
    assert default_args.build_dict is False

    # Custom options
    custom_args = load_db_module.parse_args([
        "--host", "10.0.0.1",
        "--port", "5433",
        "--user", "tester",
        "--db", "hst_prod",
        "--data-dir", "custom_output",
        "--skip-checks",
        "--build-dict",
    ])
    assert custom_args.host == "10.0.0.1"
    assert custom_args.port == 5433
    assert custom_args.user == "tester"
    assert custom_args.db == "hst_prod"
    assert custom_args.data_dir == "custom_output"
    assert custom_args.skip_checks is True
    assert custom_args.build_dict is True
