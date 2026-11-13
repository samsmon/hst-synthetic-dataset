"""Summary report for Stage 5: Injected anomalies and answer keys."""
import pandas as pd


def summarize_stage5(anomalies: pd.DataFrame, took: float) -> str:
    """Formats markdown report summarizing Stage 5 injected anomalies."""
    lines = [
        "# Stage 5 Summary",
        "",
        f"- Run time: {took:.1f} s",
        f"- Total injected anomaly labels: {len(anomalies):,}",
        "",
        "## Injected Anomalies by Type",
        "",
        "| anomaly_type | entity_type | count | share_% |",
        "|---|---|---|---|",
    ]

    tot = len(anomalies)
    if tot > 0:
        agg = anomalies.groupby(["anomaly_type", "entity_type"]).size().reset_index(name="count")
        agg.sort_values("count", ascending=False, inplace=True)
        for r in agg.itertuples():
            pct = r.count / tot * 100.0
            lines.append(f"| {r.anomaly_type} | {r.entity_type} | {r.count:,} | {pct:.1f}% |")
    else:
        lines.append("| (none) | - | 0 | 0.0% |")

    lines += [
        "",
        "## Answer Key Reference",
        "- Ground truth table: `oltp_truth.anomaly_label`",
        "- Unique constraint: `(entity_type, entity_id, anomaly_type)`",
        "- Leakage rule: labels are ground truth answers for benchmark ML task 7 (Anomaly Detection) and must never be used as operational features.",
        ""
    ]

    return "\n".join(lines)
