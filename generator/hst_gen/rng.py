"""Seeded random streams.

Each module asks for a stream by name. The stream is derived from the master
seed and a stable hash of the name, so adding or changing one module never
shifts the random numbers of another.
"""
import zlib

import numpy as np


def stream(seed: int, name: str) -> np.random.Generator:
    key = zlib.crc32(name.encode("utf-8"))
    return np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(key,)))
