"""Vectorised people data: names, ID numbers, e-mail and phone for many rows at once."""
import re

import numpy as np

from .names import CITIES, name_pools

FOREIGN_FIRST = np.array(["John", "Mary", "Wei", "Hiroshi", "Sarah", "David", "Lina", "Ahmad", "Chen", "Emma"])
FOREIGN_LAST = np.array(["Smith", "Tan", "Lee", "Wong", "Kim", "Brown", "Sato", "Lim", "Nguyen", "Khan"])
FOREIGN_NATIONALITY = np.array(["MY", "SG", "JP", "CN", "AU", "KR", "US", "GB"])

NIK_MULT = 700000000003          # odd and not a multiple of 5, so (i * mult) mod 10**14 is a permutation
PASSPORT_MULT = 1000003
PHONE_MULT = 99999989
TICKET_MULT = 310000000017       # 12 digits
ORDER_MULT = 290000000021
REF_MULT = 270000000013


def _slug(words):
    return np.array([re.sub(r"[^a-z]", "", w.lower()) for w in words])


def scatter(counter: np.ndarray, mult: int, digits: int, prefix: str = "") -> np.ndarray:
    """Unique, scattered digit strings from a counter: zero padded (counter * mult) mod 10**digits."""
    mod = 10 ** digits
    vals = (counter.astype(np.int64) * np.int64(mult)) % np.int64(mod)
    out = np.char.zfill(vals.astype("U20"), digits)
    return np.char.add(prefix, out) if prefix else out


class People:
    """Draws full names and related fields. Names are Indonesian (Faker locale), the rest is English."""

    def __init__(self, seed: int):
        male, female, last = name_pools(seed)
        self.first = {"M": np.array(male), "F": np.array(female)}
        self.first_slug = {"M": _slug(male), "F": _slug(female)}
        self.last = np.array(last)
        self.last_slug = _slug(last)
        self.cities = np.array(list(CITIES))
        w = np.array(list(CITIES.values()))
        self.city_p = w / w.sum()

    def draw(self, rng: np.random.Generator, gender: np.ndarray, middle_share: float = 0.45):
        """Returns (full name, e-mail stem) for an array of 'M' / 'F'."""
        n = len(gender)
        name = np.empty(n, dtype="U60")
        stem = np.empty(n, dtype="U40")
        last_i = rng.integers(len(self.last), size=n)
        for g in ("M", "F"):
            m = gender == g
            k = int(m.sum())
            if not k:
                continue
            pool = self.first[g]
            a = rng.integers(len(pool), size=k)
            b = rng.integers(len(pool), size=k)
            has_mid = rng.random(k) < middle_share
            base = np.char.add(pool[a], np.where(has_mid, np.char.add(" ", pool[b]), ""))
            name[m] = np.char.add(np.char.add(base, " "), self.last[last_i[m]])
            stem[m] = np.char.add(np.char.add(self.first_slug[g][a], "."), self.last_slug[last_i[m]])
        return name, stem

    def foreign(self, rng: np.random.Generator, n: int):
        full = np.char.add(np.char.add(FOREIGN_FIRST[rng.integers(len(FOREIGN_FIRST), size=n)], " "),
                           FOREIGN_LAST[rng.integers(len(FOREIGN_LAST), size=n)])
        return full, FOREIGN_NATIONALITY[rng.integers(len(FOREIGN_NATIONALITY), size=n)]

    def city(self, rng: np.random.Generator, n: int):
        return self.cities[rng.choice(len(self.cities), size=n, p=self.city_p)]
