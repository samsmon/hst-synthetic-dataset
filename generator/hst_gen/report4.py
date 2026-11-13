"""Summary report for Stage 4: FCC, refunds, bank statements and payments."""
import pandas as pd


def summarize_stage4(cards: pd.DataFrame, redemptions: pd.DataFrame, refunds: pd.DataFrame,
                     statements: pd.DataFrame, payments: pd.DataFrame, took: float) -> str:
    lines = [
        "# Stage 4 Summary",
        "",
        f"- Run time: {took:.1f} s",
        "",
        "## Frequent Customer Card (FCC)",
        f"- Total cards: {len(cards):,}",
        f"- Total redemptions: {len(redemptions):,}",
    ]

    if not cards.empty:
        type_agg = cards.groupby("card_type").agg(
            n=("id", "size"),
            avg_rem=("remaining_quota", "mean"),
            zero_rem=("remaining_quota", lambda s: int((s == 0).sum())),
        ).reset_index()
        lines += [
            "",
            "| card_type | count | share_% | avg_remaining_quota | zero_remaining |",
            "|---|---|---|---|---|",
        ]
        tot_c = len(cards)
        for r in type_agg.itertuples():
            pct = r.n / tot_c * 100
            lines.append(f"| {r.card_type} | {r.n:,} | {pct:.1f} | {r.avg_rem:.2f} | {r.zero_rem:,} |")

    lines += [
        "",
        "## Refunds and Cancellations",
        f"- Total refunds: {len(refunds):,}",
    ]
    if not refunds.empty:
        tot_amt = refunds["refund_amount"].sum()
        tot_fee = refunds["refund_fee"].sum()
        lines.append(f"- Total refunded amount: Rp {tot_amt:,.0f}")
        lines.append(f"- Total refund fee retained: Rp {tot_fee:,.0f}")
        lines += [
            "",
            "| reason | count | share_% | avg_refund_amount | avg_fee |",
            "|---|---|---|---|---|",
        ]
        r_agg = refunds.groupby("reason").agg(
            n=("id", "size"),
            tot_amt=("refund_amount", "mean"),
            tot_fee=("refund_fee", "mean"),
        ).reset_index()
        tot_r = len(refunds)
        for r in r_agg.itertuples():
            pct = r.n / tot_r * 100
            lines.append(f"| {r.reason} | {r.n:,} | {pct:.1f} | Rp {r.tot_amt:,.0f} | Rp {r.tot_fee:,.0f} |")

    lines += [
        "",
        "## Bank Statement",
        f"- Total statement lines: {len(statements):,}",
    ]
    if not statements.empty:
        lines += [
            "",
            "| transaction_code | direction | count | total_amount |",
            "|---|---|---|---|",
        ]
        s_agg = statements.groupby(["transaction_code", "direction"]).agg(
            n=("id", "size"),
            tot=("amount", "sum"),
        ).reset_index()
        for r in s_agg.itertuples():
            lines.append(f"| {r.transaction_code} | {r.direction} | {r.n:,} | Rp {r.tot:,.0f} |")

        lines += [
            "",
            "### Balances by Account",
            "| account_no | closing_balance |",
            "|---|---|",
        ]
        for acc, grp in statements.groupby("account_no"):
            close_bal = grp.iloc[-1]["balance"]
            lines.append(f"| {acc} | Rp {close_bal:,.2f} |")

    lines += [
        "",
        "## Group Booking Payments",
        f"- Total allocations: {len(payments):,}",
    ]
    if not payments.empty:
        lines += [
            "",
            "| payment_type | count | total_allocated |",
            "|---|---|---|",
        ]
        p_agg = payments.groupby("payment_type").agg(
            n=("group_booking_id", "size"),
            tot=("allocated_amount", "sum"),
        ).reset_index()
        for r in p_agg.itertuples():
            lines.append(f"| {r.payment_type} | {r.n:,} | Rp {r.tot:,.0f} |")

    return "\n".join(lines) + "\n"
