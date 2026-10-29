"""Prueba de latencia local del pipeline completo (H2-T20, RNF-102)."""

from __future__ import annotations

import time

from app.engine.pipeline import run_rules
from app.normalization import normalize
from app.scoring.scorer import calculate_score, classify_risk

#: Presupuesto máximo exigido por TC-RNF-102.
MAX_LATENCY_MS = 50.0


def test_pipeline_local_bajo_50_ms() -> None:
    parsed = normalize(
        "http://secure-login.example.com:8080/account/verify"
        "?next=https://evil.example&token=abcdef0123456789"
    )

    started_at = time.perf_counter()
    results = run_rules(parsed)
    score = calculate_score(results)
    classify_risk(score)
    elapsed_ms = (time.perf_counter() - started_at) * 1000

    assert elapsed_ms <= MAX_LATENCY_MS, f"latencia {elapsed_ms:.2f} ms"
