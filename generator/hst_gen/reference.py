"""Reference data that mirrors sql/03_reference_data.sql (a test compares the two)."""
import numpy as np
import pandas as pd

STATIONS = {1: "HLM", 2: "KRW", 3: "PDL", 4: "TGL"}
CLASSES = ["economy", "premium", "business", "first"]
CHANNEL_CODES = {1: "COUNTER", 2: "GROUP", 3: "FCC", 4: "AGENT", 5: "APP", 6: "WEB"}
STAFFED_CHANNELS = (1, 2, 3)

_BASE_FARES = {            # route id -> price per class, version 1 (2020 to 2022)
    1: [200000, 250000, 350000, 500000],
    2: [100000, 130000, 180000, 260000],
    3: [150000, 190000, 270000, 390000],
}


def fares() -> pd.DataFrame:
    rows = []
    for v, (valid_from, valid_to, factor) in enumerate([("2020-01-01", "2022-12-31", 1.0), ("2023-01-01", None, 1.1)]):
        for route, prices in _BASE_FARES.items():
            for cls, price in zip(CLASSES, prices):
                price = int(round(price * factor / 1000) * 1000) if factor != 1.0 else price
                rows.append({"id": len(rows) + 1, "route_id": route, "seat_class": cls, "base_price": price,
                             "valid_from": pd.Timestamp(valid_from), "valid_to": pd.Timestamp(valid_to) if valid_to else pd.NaT})
    return pd.DataFrame(rows)


def route_stations(route: int, direction: int, far_is_tgl: np.ndarray):
    """Origin and destination station ids for a route and direction (0 to_bandung, 1 to_jakarta).

    Route 1 runs Halim to Bandung, route 2 Halim to Karawang, route 3 Karawang to Bandung.
    far_is_tgl chooses Tegalluar (True) or Padalarang (False) as the Bandung end.
    """
    far = np.where(far_is_tgl, 4, 3)
    near = {1: np.full(far.shape, 1), 2: np.full(far.shape, 1), 3: np.full(far.shape, 2)}[route]
    if route == 2:
        far = np.full(far.shape, 2)
    return (near, far) if direction == 0 else (far, near)
