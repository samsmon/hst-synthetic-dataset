"""Name pools for people and organisations (Indonesian names, English everything else)."""
import re

import numpy as np
from faker import Faker

CITIES = {
    "Jakarta": 0.22, "Bandung": 0.20, "Bekasi": 0.08, "Bogor": 0.06, "Depok": 0.05, "Tangerang": 0.05,
    "Karawang": 0.06, "Cimahi": 0.04, "Cirebon": 0.03, "Purwakarta": 0.03, "Cianjur": 0.02,
    "Sukabumi": 0.02, "Garut": 0.02, "Tasikmalaya": 0.02, "Subang": 0.02, "Yogyakarta": 0.03,
    "Semarang": 0.02, "Surabaya": 0.03,
}

WORDS = ["Maju", "Jaya", "Sinar", "Cahaya", "Berkah", "Mitra", "Karya", "Mandiri", "Abadi", "Bersama",
         "Sejahtera", "Harapan", "Utama", "Prima", "Nusantara", "Global", "Sentosa", "Makmur", "Surya",
         "Bintang", "Garuda", "Pelangi", "Lestari", "Gemilang", "Cipta", "Handal", "Perkasa", "Wijaya",
         "Tunas", "Mulia", "Bumi", "Samudra", "Cakra", "Dharma", "Tirta", "Wira", "Anugerah", "Citra"]
SECTORS = ["Logistik", "Teknologi", "Konstruksi", "Energi", "Perdagangan", "Pangan", "Tekstil", "Otomotif",
           "Farmasi", "Properti", "Media", "Telekomunikasi", "Manufaktur", "Konsultan", "Percetakan"]
TRAVEL = ["Tour & Travel", "Wisata", "Holiday", "Travel", "Trans Wisata", "Nusantara Tour"]
HOBBIES = ["Sepeda", "Fotografi", "Lari", "Pendaki", "Musik", "Literasi", "Otomotif", "Kuliner", "Seni"]
GOV_UNITS = ["Balai Pelatihan Kerja", "Sekretariat Daerah", "Unit Layanan Terpadu", "Balai Pengembangan Pariwisata",
             "Dinas Kebudayaan", "Balai Latihan Aparatur"]


def name_pools(seed: int):
    """Sorted pools of male first, female first and last names from Faker's Indonesian locale."""
    f = Faker("id_ID")
    f.seed_instance(seed)
    male = sorted({f.first_name_male() for _ in range(4000)})
    female = sorted({f.first_name_female() for _ in range(4000)})
    last = sorted({f.last_name() for _ in range(4000)})
    return male, female, last


def person_names(rng: np.random.Generator, genders, pools, middle_share=0.45):
    """Full names for an array of genders ('M' or 'F'): first, optional second given name, last."""
    male, female, last = pools
    out = []
    for g in genders:
        first_pool = male if g == "M" else female
        parts = [first_pool[rng.integers(len(first_pool))]]
        if rng.random() < middle_share:
            parts.append(first_pool[rng.integers(len(first_pool))])
        parts.append(last[rng.integers(len(last))])
        out.append(" ".join(parts))
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def company_name(rng: np.random.Generator, kind: str, city: str) -> str:
    w = lambda: WORDS[rng.integers(len(WORDS))]                       # noqa: E731
    if kind == "travel_agency":
        return f"{w()} {w()} {TRAVEL[rng.integers(len(TRAVEL))]}"
    if kind == "corporate":
        return f"PT {w()} {w()} {SECTORS[rng.integers(len(SECTORS))]}"
    if kind == "school":
        style = rng.integers(4)
        if style == 0:
            return f"SMA Negeri {rng.integers(1, 30)} {city}"
        if style == 1:
            return f"SMK {w()} {city}"
        if style == 2:
            return f"Universitas {w()} {w()}"
        return f"SMP Islam Al-{w()}"
    if kind == "government":
        return f"{GOV_UNITS[rng.integers(len(GOV_UNITS))]} {city}"
    return f"{['Komunitas', 'Paguyuban', 'Klub'][rng.integers(3)]} {HOBBIES[rng.integers(len(HOBBIES))]} {city}"
