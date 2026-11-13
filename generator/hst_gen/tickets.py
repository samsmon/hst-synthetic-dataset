"""Stage 3: all tickets, bookings and new customers of one month."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import rng as rnglib
from .bookings import Ids, assign_directions, booking_frame, pack_month
from .customers import CustomerBook
from .pricing import demand_discount_pct, discount_amount, fare_lookup, peak_uplift, round_price, step_discount
from .reference import STAFFED_CHANNELS, route_stations
from .refunds import process_status_and_refunds
from .vecnames import ORDER_MULT, REF_MULT, TICKET_MULT, NIK_MULT, People, scatter

DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
OPEN_DATE = np.datetime64("2019-12-01")
TIME_STR = np.array([f"{m // 60:02d}:{m % 60:02d}:00" for m in range(1440)])


@dataclass
class State:
    ctx: object
    ids: Ids = field(default_factory=Ids)
    people: People = None
    book: CustomerBook = None

    def __post_init__(self):
        self.people = People(self.ctx.seed)
        self.book = CustomerBook(self.ctx.cfg, self.people, self.ids)


def _pick(rng, mapping: dict, n: int, as_int=False):
    keys = np.array(list(mapping))
    p = np.array(list(mapping.values()), dtype=float)
    out = keys[rng.choice(len(keys), size=n, p=p / p.sum())]
    return out.astype(int) if as_int else out


def _dstr(a: np.ndarray) -> np.ndarray:
    return np.datetime_as_string(a, unit="D")


def generate_month(st: State, month_id: int) -> dict:
    ctx = st.ctx
    cfg, s3 = ctx.cfg, ctx.cfg["stage3"]
    rng = rnglib.stream(ctx.seed, f"stage3.{month_id}")
    cal = ctx.tables["cal"]
    days = ctx.month_rows[month_id]
    nd, dates_m = len(days), ctx.dates[days]
    month_start = dates_m[0].astype("datetime64[M]").astype("datetime64[D]")
    G, I = ctx.group[days].copy(), ctx.individual[days].copy()
    tot = ctx.tickets[days].sum(axis=1)
    share_b = np.array([cfg["trips"]["to_bandung_share"][k] for k in DOW_KEYS])[cal["dow"].values[days]]
    want_b = np.round(tot * share_b).astype(np.int64)
    want_j = tot - want_b

    # ------------------------------------------------------------ group bookings
    bookings, converted = pack_month(rng, G, s3["group"])
    I += converted
    used = assign_directions(rng, bookings, want_b, want_j, s3["group"]["first_leg_to_bandung"]) if bookings else np.zeros((nd, 2), dtype=np.int64)
    bk = booking_frame(ctx, rng, bookings, days, st.ids) if bookings else None
    nb = len(bookings)
    leg_b = np.array([i for i, b in enumerate(bookings) for _ in b["days"]], dtype=np.int64)
    leg_day = np.array([d for b in bookings for d in b["days"]], dtype=np.int64)
    leg_dir = np.array([k for b in bookings for k in b["dirs"]], dtype=np.int64)
    leg_no = np.array([j for b in bookings for j in range(len(b["days"]))], dtype=np.int64)
    leg_size = np.array([b["size"] for b in bookings for _ in b["days"]], dtype=np.int64) if nb else np.array([], dtype=np.int64)
    pax_start = np.concatenate([[0], np.cumsum([b["size"] for b in bookings])]) if nb else np.array([0])
    n_g = int(leg_size.sum())
    g_book = np.repeat(leg_b, leg_size)
    g_day, g_dir, g_leg = np.repeat(leg_day, leg_size), np.repeat(leg_dir, leg_size), np.repeat(leg_no, leg_size)
    leg_start = np.concatenate([[0], np.cumsum(leg_size)[:-1]]) if nb else np.array([], dtype=np.int64)
    g_pax = pax_start[g_book] + (np.arange(n_g) - np.repeat(leg_start, leg_size))

    # ------------------------------------------------------------- individual cells
    ind_total = I.sum(axis=1)
    ind_b = np.zeros_like(I)
    for d in range(nd):
        k = int(np.clip(want_b[d] - used[d, 0], 0, ind_total[d]))
        if k > 0:
            ind_b[d] = rng.multivariate_hypergeometric(I[d], k)
    counts = np.stack([ind_b, I - ind_b], axis=2)                    # (day, route, direction)
    dg, rg, kg = np.indices(counts.shape)
    flat = counts.ravel()
    i_day, i_route, i_dir = np.repeat(dg.ravel(), flat), np.repeat(rg.ravel() + 1, flat), np.repeat(kg.ravel(), flat)
    n_i = len(i_day)

    # ----------------------------------------------------- combine into one ticket table
    N = n_i + n_g
    kind = np.concatenate([np.zeros(n_i, dtype=np.int8), np.ones(n_g, dtype=np.int8)])
    day = np.concatenate([i_day, g_day])
    direction = np.concatenate([i_dir, g_dir])
    route = np.concatenate([i_route, bk["route_id"].to_numpy()[g_book] if nb else np.array([], dtype=np.int64)])
    booking = np.concatenate([np.full(n_i, -1, dtype=np.int64), g_book])
    leg = np.concatenate([np.zeros(n_i, dtype=np.int64), g_leg])
    gday = days[day]
    dep_date = ctx.dates[gday]

    # --------------------------------------------------------------- stations and trips
    tgl = rng.random(N) < s3["stations"]["far_end_share"]["tgl"]
    origin, dest = np.zeros(N, dtype=np.int64), np.zeros(N, dtype=np.int64)
    for r in (1, 2, 3):
        for k in (0, 1):
            m = (route == r) & (direction == k)
            if m.any():
                origin[m], dest[m] = route_stations(r, k, tgl[m])
    trip_id, trip_dep = np.zeros(N, dtype=np.int64), np.zeros(N, dtype=np.int64)
    key = gday * 2 + direction
    order = np.argsort(key, kind="stable")
    uniq, first, cnt = np.unique(key[order], return_index=True, return_counts=True)
    for kk, f, c in zip(uniq, first, cnt):
        rows = order[f:f + c]
        tids, cap, dep = ctx.trips_by_key[(int(kk // 2), int(kk % 2))]
        exact = c * cap / cap.sum()
        base = np.floor(exact).astype(np.int64)
        base[np.argsort(-(exact - base))[: int(c - base.sum())]] += 1
        pick = np.repeat(np.arange(len(tids)), base)[rng.permutation(c)]
        trip_id[rows], trip_dep[rows] = tids[pick], dep[pick]
    off = np.zeros(5, dtype=np.int64)
    for sid, mins in s3["stations"]["offset_minutes"].items():
        off[int(sid)] = mins
    full = int(off.max())
    dep_off = np.where(direction == 0, off[origin], full - off[origin])
    arr_off = np.where(direction == 0, off[dest], full - off[dest])
    dep_min, arr_min = trip_dep + dep_off, trip_dep + arr_off

    # -------------------------------------------------------- who travels, channel, class
    cust = {"customer_id": np.zeros(N, dtype=np.int64), "name": np.empty(N, dtype="U60"), "id_number": np.empty(N, dtype="U20"),
            "nationality": np.full(N, "ID", dtype="U2"), "segment": np.full(N, -1), "has_fcc": np.zeros(N, dtype=bool)}
    new_customers = None
    if n_i:
        ind, new_customers = st.book.assign(rng, month_start, i_route)
        created = ind.pop("created")
        for kname, arr in ind.items():
            cust[kname][:n_i] = arr
    pax = int(pax_start[-1])
    if n_g:
        gender = np.where(rng.random(pax) < 0.5, "M", "F")
        pname, _ = st.people.draw(rng, gender)
        pid = np.char.add("99", scatter(st.ids.take("nik", pax), NIK_MULT, 14))
        cust["name"][n_i:], cust["id_number"][n_i:] = pname[g_pax], pid[g_pax]

    year = int(dates_m[0].astype("datetime64[Y]").astype(int) + 1970)
    ind_cfg = s3["individual"]
    channel = np.zeros(N, dtype=np.int64)
    channel[:n_i] = _pick(rng, ind_cfg["channel_by_year"][year], n_i, as_int=True)
    card = cust["has_fcc"][:n_i] & (rng.random(n_i) < s3["customers"]["fcc_ticket_share"])
    channel[:n_i][card] = 3
    if n_g:
        channel[n_i:] = bk["channel"].to_numpy()[g_book]
    seat = np.empty(N, dtype="U10")
    commuter = cust["segment"][:n_i] == 0
    seat[:n_i] = np.where(commuter, _pick(rng, ind_cfg["commuter_seat_class"], n_i), _pick(rng, ind_cfg["seat_class"], n_i))
    if n_g:
        seat[n_i:] = bk["seat_class"].to_numpy()[g_book]

    # -------------------------------------------------------------- purchase date and price
    lead_mean = np.zeros(7)
    for ch, mean in ind_cfg["lead_days_mean"].items():
        lead_mean[int(ch)] = mean
    lead = np.zeros(N, dtype=np.int64)
    lead[:n_i] = np.floor(rng.exponential(lead_mean[channel[:n_i]])).astype(np.int64)
    purchase = np.maximum(dep_date - lead.astype("timedelta64[D]"), OPEN_DATE)
    if n_i:                                                  # nobody buys before their account exists
        purchase[:n_i] = np.maximum(purchase[:n_i], np.where(np.isnat(created), OPEN_DATE, created))
        lead[:n_i] = (dep_date[:n_i] - purchase[:n_i]).astype(np.int64)
    if n_g:
        off_lo, off_hi = s3["group"]["purchase_offset_days"]
        doc = bk["document_date"].to_numpy().astype("datetime64[D]")[g_book]
        purchase[n_i:] = np.minimum(doc + rng.integers(off_lo, off_hi + 1, size=n_g).astype("timedelta64[D]"), dep_date[n_i:])
        lead[n_i:] = (dep_date[n_i:] - purchase[n_i:]).astype(np.int64)

    fare_id, fare_price = fare_lookup(ctx.fares, route, seat, purchase)
    load = ctx.load[gday, direction]
    base_price = round_price(fare_price * (1 + peak_uplift(load, cfg)))
    base_pct = demand_discount_pct(load, cfg)
    base_pct[:n_i] += step_discount(lead[:n_i], ind_cfg["early_bird_pct"])
    if n_g:
        base_pct[n_i:] += step_discount(leg_size_per_ticket := bk["size"].to_numpy()[g_book], s3["group"]["tier_discount_pct"])
    pidx = ctx.day_index(purchase[:n_i])
    use_card = channel[:n_i] == 3
    promo_pct = np.zeros(N)
    promo_id = np.zeros(N, dtype=np.int64)
    promo_pct[:n_i] = np.where(use_card, ctx.fcc_promo[0][pidx, i_route - 1], ctx.ind_promo[0][pidx, i_route - 1])
    promo_id[:n_i] = np.where(use_card, ctx.fcc_promo[1][pidx, i_route - 1], ctx.ind_promo[1][pidx, i_route - 1])
    before_period = purchase[:n_i] < ctx.dates[0]            # sold in the opening weeks: no promo exists yet
    promo_pct[:n_i] = np.where(before_period, 0.0, promo_pct[:n_i])
    promo_id[:n_i] = np.where(before_period, 0, promo_id[:n_i])
    if n_g:
        mean_base = np.bincount(g_book, weights=base_pct[n_i:], minlength=nb) / np.maximum(np.bincount(g_book, minlength=nb), 1)
        won = bk["promo_pct"].to_numpy() > mean_base
        promo_pct[n_i:] = np.where(won, bk["promo_pct"].to_numpy(), 0.0)[g_book]
        promo_id[n_i:] = np.where(won, bk["promo_id"].to_numpy(), 0)[g_book]
        bk["promo_id"] = np.where(won, bk["promo_id"].to_numpy(), 0)
    wins = promo_pct > base_pct
    pct = np.minimum(np.round(np.where(wins, promo_pct, base_pct) * 2) / 2, s3["pricing"]["max_discount_pct"])
    promo_id = np.where(wins, promo_id, 0)
    disc = discount_amount(base_price, pct)
    fee_by = np.zeros(7, dtype=np.int64)
    for ch, v in s3["pricing"]["service_fee"].items():
        fee_by[int(ch)] = v
    fee = fee_by[channel]
    total = base_price - disc + fee

    # ----------------------------------------------------- payment, staff, identifiers
    method = np.empty(N, dtype="U16")
    for ch, mapping in s3["pricing"]["payment_method"].items():
        m = channel == int(ch)
        if m.any():
            method[m] = _pick(rng, mapping, int(m.sum()))
    pay_ref = np.where(np.isin(method, ["cash", "bank_transfer", "fcc_quota", "agent_deposit"]), "",
                       np.char.add("PR", scatter(st.ids.take("ref", N), REF_MULT, 12)))
    plat_ref = np.where(np.isin(channel, [4, 5, 6]) & (pay_ref != ""), np.char.add("PL", np.char.replace(pay_ref, "PR", "")), "")
    emp, issue_station = np.zeros(N, dtype=np.int64), np.zeros(N, dtype=np.int64)
    for ch in STAFFED_CHANNELS:
        m = np.flatnonzero(channel == ch)
        if m.size:
            want = np.where(rng.random(m.size) < 0.5, 1, 4) if ch == 2 else origin[m]
            emp[m], issue_station[m] = ctx.staff[ch].pick(purchase[m], rng, want)

    # ----------------------------------------------------------- sort and number the rows
    srt = np.lexsort((kind, direction, route, dep_min, gday))
    take = lambda a: a[srt]                                                           # noqa: E731
    tid = st.ids.take("ticket", N)
    seq_no = np.arange(1, N + 1, dtype=np.int64)
    booking_s, leg_s, kind_s, day_s = take(booking), take(leg), take(kind), take(day)
    if nb:
        bk["period"] = np.array([f"{str(d)[:7]}" for d in ctx.dates[bk["first_day"].to_numpy()]])
        bk["booking_no"] = np.char.add(np.char.add("BAK-", np.char.add(bk["document_date"].to_numpy().astype("datetime64[Y]").astype(str), "-")),
                                       np.char.zfill(bk["id"].to_numpy().astype("U10"), 6))
    order_new = np.char.add("O", scatter(st.ids.take("order", N), ORDER_MULT, 11))
    if nb:
        group_order = np.char.add(np.char.add(bk["booking_no"].to_numpy()[np.maximum(booking_s, 0)], "-L"), (leg_s + 1).astype("U2"))
        order_id = np.where(kind_s == 1, group_order, take(order_new))
    else:
        order_id = take(order_new)
    period = np.array([str(d)[:7] for d in dates_m])[day_s]

    book_id = np.zeros(N, dtype=np.int64)                  # in the original row order, sorted once when the table is built
    if nb:
        book_id = np.where(booking >= 0, bk["id"].to_numpy()[np.maximum(booking, 0)], 0)
    group_tickets = pd.DataFrame({"booking_idx": booking_s[kind_s == 1], "ticket_id": tid[kind_s == 1]})

    # --------------------------------------------------------- booking totals and status
    detail = truth = None
    if nb:
        agg = pd.DataFrame({"b": booking_s[kind_s == 1], "total": take(total)[kind_s == 1], "disc": take(disc)[kind_s == 1]}).groupby("b").sum()
        bk["total_amount"] = agg["total"].reindex(range(nb)).to_numpy()
        bk["discount_amount"] = agg["disc"].reindex(range(nb)).to_numpy()
        as_of = np.datetime64(s3["as_of"])
        pend_from = as_of - np.timedelta64(s3["pending"]["last_days"], "D")
        first_dep = ctx.dates[bk["first_day"].to_numpy()]
        pending = (first_dep > pend_from) | (rng.random(nb) < s3["pending"]["random_share"])
        bk["status"] = np.where(pending, "pending", "checked")
        last_dep = ctx.dates[bk["last_day"].to_numpy()]
        creator, _ = ctx.staff["group_creator"].pick(bk["document_date"].to_numpy().astype("datetime64[D]"), rng)
        verifier, _ = ctx.staff["verifier"].pick(last_dep + np.timedelta64(5, "D"), rng)
        bk["created_by"], bk["verified_by"] = creator, np.where(pending, 0, verifier)
        book_id = np.where(np.isin(booking, np.flatnonzero(pending)), 0, book_id)          # pending bookings are not classified yet
        truth = pd.DataFrame({"ticket_sales_id": tid[kind_s == 1],
                              "group_booking_id": bk["id"].to_numpy()[booking_s[kind_s == 1]]})
        truth = truth[np.isin(booking_s[kind_s == 1], np.flatnonzero(pending))]
        variant = _pick(rng, s3["group"]["counterparty_variants"], nb)
        cname = ctx.tables["company"]["name"].to_numpy()[bk["company_idx"].to_numpy()].astype("U80")
        short = np.array([" ".join(x.split()[:2]) for x in cname])
        bk["counterparty_name"] = np.where(variant == "upper", np.char.upper(cname), np.where(variant == "short", short, cname))
        bk["has_proof"] = rng.random(nb) < np.where(pending, 0.4, 0.9)
        bk["has_manifest"] = rng.random(nb) < np.where(pending, 0.6, 0.95)
        bk["notes"] = np.where(rng.random(nb) < 0.05, "manifest revised", "")
        bk["file_name"] = np.char.add(bk["booking_no"].to_numpy(), ".pdf")
        bk["file_path"] = np.char.add(np.char.add(np.char.add("bak/", bk["period"].to_numpy()), "/"), bk["file_name"].to_numpy())
        bk["created_at"] = np.char.add(_dstr(bk["document_date"].to_numpy().astype("datetime64[D]")), " 09:00:00")

    ref_rng = rnglib.stream(ctx.seed, f"refunds.{month_id}")
    ref_cfg = cfg.get("stage4", {}).get("refunds")
    if ref_cfg is not None and "cs" in ctx.staff:
        ticket_status, refund_df = process_status_and_refunds(
            tid, take(purchase), take(dep_date), take(total), take(channel),
            kind_s == 1, np.datetime64(s3["as_of"]), ref_cfg, ctx.staff["cs"], ref_rng, st.ids)
    else:
        ticket_status = np.where(take(dep_date) <= np.datetime64(s3["as_of"]), "used", "issued")
        refund_df = None

    nullable = lambda a: np.where(a == 0, "", a.astype("U20"))                         # noqa: E731
    tickets = pd.DataFrame({
        "id": tid, "seq_no": seq_no, "period": period, "passenger_name": take(cust["name"]),
        "passenger_id_number": take(cust["id_number"]), "customer_id": nullable(take(cust["customer_id"])),
        "group_booking_id": nullable(take(book_id)), "nationality": take(cust["nationality"]), "order_id": order_id,
        "ticket_no": np.char.add("T", scatter(tid, TICKET_MULT, 12)),
        "status": ticket_status, "trip_id": take(trip_id),
        "route_id": take(route), "purchase_date": _dstr(take(purchase)), "departure_date": _dstr(take(dep_date)),
        "departure_time": TIME_STR[take(dep_min)], "origin_station_id": take(origin), "destination_station_id": take(dest),
        "arrival_date": _dstr(take(dep_date)), "arrival_time": TIME_STR[take(arr_min)], "seat_class": take(seat),
        "fare_id": take(fare_id), "base_price": take(base_price), "discount_pct": take(pct), "discount_amount": take(disc),
        "service_fee_amount": take(fee), "total_price": take(total), "promo_id": nullable(take(promo_id)),
        "payment_method": take(method), "payment_ref": take(pay_ref), "platform_payment_ref": take(plat_ref),
        "sales_channel_id": take(channel), "issued_by_employee_id": nullable(take(emp)),
        "issue_station_id": nullable(take(issue_station)),
    })

    out = {"ticket_sales": tickets, "ticket_group_truth": truth, "n_individual": n_i, "n_group": n_g,
           "segment": take(cust["segment"]), "channel": take(channel), "pending": 0 if not nb else int(pending.sum())}
    if refund_df is not None:
        out["refund"] = refund_df
    if nb:
        det_n = len(leg_day)
        out["group_booking_detail"] = pd.DataFrame({
            "id": st.ids.take("detail", det_n), "group_booking_id": bk["id"].to_numpy()[leg_b], "departure_date": _dstr(ctx.dates[days[leg_day]])})
        out["group_booking"] = pd.DataFrame({
            "id": bk["id"], "booking_no": bk["booking_no"], "company_id": bk["company_id"], "counterparty_name": bk["counterparty_name"],
            "period": bk["period"], "document_date": _dstr(bk["document_date"].to_numpy().astype("datetime64[D]")),
            "payment_due_date": _dstr(bk["payment_due_date"].to_numpy().astype("datetime64[D]")), "route_id": bk["route_id"],
            "passenger_count": bk["size"], "total_amount": bk["total_amount"], "discount_amount": bk["discount_amount"],
            "promo_id": nullable(bk["promo_id"].to_numpy()), "status": bk["status"], "has_transfer_proof": np.where(bk["has_proof"], "t", "f"),
            "has_manifest": np.where(bk["has_manifest"], "t", "f"), "notes": bk["notes"], "file_name": bk["file_name"],
            "file_path": bk["file_path"], "created_by_employee_id": nullable(bk["created_by"].to_numpy()),
            "verified_by_employee_id": nullable(bk["verified_by"].to_numpy()), "created_at": bk["created_at"],
        })
    if new_customers is not None:
        firsts = pd.DataFrame({"id": take(cust["customer_id"]), "d": take(purchase)})
        firsts = firsts[firsts["id"] > 0].groupby("id")["d"].min()
        nc = new_customers.copy()
        nc["birth_date"] = _dstr(nc["birth_date"].to_numpy().astype("datetime64[D]"))
        stamp = firsts.reindex(nc["id"]).to_numpy().astype("datetime64[D]")
        st.book.register(nc["id"].to_numpy(), stamp)
        nc["created_at"] = np.char.add(_dstr(stamp), np.char.add(" ", TIME_STR[360 + rng.integers(0, 960, size=len(nc))]))
        out["customer"] = nc
    return out
