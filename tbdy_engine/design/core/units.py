from __future__ import annotations

def mm2_to_m2(x: float) -> float:
    return x / 1_000_000.0

def cm2_to_m2(x: float) -> float:
    return x / 10_000.0

def n_to_kn(x: float) -> float:
    return x / 1000.0

def kn_to_n(x: float) -> float:
    return x * 1000.0
