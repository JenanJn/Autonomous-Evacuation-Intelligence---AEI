"""
AEI — Inference Performance Benchmark
========================================
Measures model loading, preprocessing, single-record inference and batch
inference latency separately, using the saved RandomForest artefact.

Methodology
-----------
* Each timing phase is measured with time.perf_counter() (highest resolution
  available on the platform).
* Each phase is repeated N_REPEATS times; we report median and p95.
* The first run is a warm-up and is excluded from statistics — it includes
  OS file-cache cold-start effects that are not representative.
* Batch sizes measured: 1, 10, 50, 200 rows.
* Data source: SYNTHETIC — timings are hardware-dependent and do NOT
  represent production performance on a real dataset.

Targets (from project requirements — check against actual output)
-----------------------------------------------------------------
  Local model inference:          < 1 s   (target)
  Small-scenario end-to-end:      < 3 s   (target)

These are aspirational targets, not guarantees.  Report actual measured
values and the hardware context; do not cherry-pick the fastest run.

Run from AEI/:
    python scripts/benchmark_inference.py
"""
from __future__ import annotations

import pathlib
import statistics
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))

import numpy as np
import pandas as pd

from data_pipeline.ingestion import load_csv
from fixtures.make_synthetic_fixture import make_clean_fixture, SIMULATED_DIR
from prediction.model_loader import load_model_bundle
from prediction.predict import predict_batch

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODELS_DIR    = _ROOT / "models"
RF_ARTEFACT   = MODELS_DIR / "RandomForest_v0.1.0"
N_REPEATS     = 20       # repeats per phase (first is warm-up, excluded)
BATCH_SIZES   = [1, 10, 50, 200]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stats(times_s: list[float]) -> dict:
    """Return median and p95 from a list of second-valued timings."""
    times_ms = [t * 1000 for t in times_s]
    return {
        "median_ms": round(statistics.median(times_ms), 3),
        "p95_ms":    round(sorted(times_ms)[int(len(times_ms) * 0.95)], 3),
        "min_ms":    round(min(times_ms), 3),
        "max_ms":    round(max(times_ms), 3),
        "n":         len(times_ms),
    }


def _row_to_df(bundle, n: int) -> pd.DataFrame:
    """Build an n-row DataFrame matching the model's feature schema."""
    rng = np.random.default_rng(0)
    feat_cols = [c.replace("_scaled", "") for c in bundle.metadata.feature_cols
                 if c.endswith("_scaled")]
    data = {col: rng.uniform(0.0, 10.0, n) for col in feat_cols}
    data["zone_id"] = [f"BENCH_{i:04d}" for i in range(n)]
    return pd.DataFrame(data)


def _section(title: str) -> None:
    print()
    print("-" * 56)
    print(f"  {title}")
    print("-" * 56)


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def benchmark_model_loading() -> dict:
    """Measure cold load from disk (file already in OS cache after first run)."""
    times = []
    for i in range(N_REPEATS + 1):
        t0 = time.perf_counter()
        _ = load_model_bundle(RF_ARTEFACT)
        elapsed = time.perf_counter() - t0
        if i > 0:           # skip warm-up
            times.append(elapsed)
    return _stats(times)


def benchmark_preprocessing(bundle, n_rows: int = 50) -> dict:
    """Measure only the preprocessing phase (cleaning + feature engineering)."""
    from data_pipeline.cleaning import apply_cleaning_pipeline
    from data_pipeline.feature_engineering import apply_feature_pipeline, build_model_feature_matrix

    df = _row_to_df(bundle, n_rows)
    times = []
    for i in range(N_REPEATS + 1):
        t0 = time.perf_counter()
        df_c = apply_cleaning_pipeline(df, bundle.cleaning_stats,
                                       drop_target_nulls=False)
        df_e = apply_feature_pipeline(df_c, bundle.feature_stats)
        X, _ = build_model_feature_matrix(df_e,
                                          feature_cols=bundle.metadata.feature_cols)
        elapsed = time.perf_counter() - t0
        if i > 0:
            times.append(elapsed)
    return _stats(times)


def benchmark_inference_only(bundle, n_rows: int = 50) -> dict:
    """Measure only model.predict() — after preprocessing is already done."""
    from data_pipeline.cleaning import apply_cleaning_pipeline
    from data_pipeline.feature_engineering import apply_feature_pipeline, build_model_feature_matrix

    df = _row_to_df(bundle, n_rows)
    df_c = apply_cleaning_pipeline(df, bundle.cleaning_stats,
                                   drop_target_nulls=False)
    df_e = apply_feature_pipeline(df_c, bundle.feature_stats)
    X, _ = build_model_feature_matrix(df_e,
                                      feature_cols=bundle.metadata.feature_cols)

    times = []
    for i in range(N_REPEATS + 1):
        t0 = time.perf_counter()
        _ = bundle.model.predict(X)
        elapsed = time.perf_counter() - t0
        if i > 0:
            times.append(elapsed)
    return _stats(times)


def benchmark_end_to_end_batch(bundle, n_rows: int) -> dict:
    """
    Measure the full predict_batch() call including preprocessing, inference
    and Pydantic schema construction.
    """
    df = _row_to_df(bundle, n_rows)
    times = []
    for i in range(N_REPEATS + 1):
        t0 = time.perf_counter()
        _ = predict_batch(df, bundle)
        elapsed = time.perf_counter() - t0
        if i > 0:
            times.append(elapsed)
    return _stats(times)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _fmt(stats: dict) -> str:
    return (f"median={stats['median_ms']:.2f} ms  "
            f"p95={stats['p95_ms']:.2f} ms  "
            f"min={stats['min_ms']:.2f} ms  "
            f"(n={stats['n']})")


def main() -> None:
    print()
    print("=" * 56)
    print("  AEI — Inference Benchmark")
    print("  DATA: SYNTHETIC — timings are hardware-dependent")
    print("=" * 56)

    if not RF_ARTEFACT.exists():
        print(f"\nERROR: Artefact not found: {RF_ARTEFACT}")
        print("Run scripts/run_training.py first.")
        sys.exit(1)

    # ── Phase 0: Model loading ─────────────────────────────────────────────
    _section("Phase 0: Model loading from disk")
    load_stats = benchmark_model_loading()
    print(f"  {_fmt(load_stats)}")
    target_ok = load_stats["median_ms"] < 1000
    print(f"  Target < 1000 ms : {'PASS' if target_ok else 'NEEDS REVIEW'}")

    # Load once for remaining phases (already warmed up)
    bundle = load_model_bundle(RF_ARTEFACT)
    print(f"\n  Loaded model : {bundle.metadata.model_name} v{bundle.metadata.model_version}")
    print(f"  Data source  : {bundle.metadata.data_source}")
    print(f"  Features     : {len(bundle.metadata.feature_cols)}")

    # ── Phase 1: Preprocessing only (50 rows) ─────────────────────────────
    _section("Phase 1: Preprocessing only (50 rows)")
    pre_stats = benchmark_preprocessing(bundle, n_rows=50)
    print(f"  {_fmt(pre_stats)}")

    # ── Phase 2: Inference only (50 rows) ─────────────────────────────────
    _section("Phase 2: model.predict() only (50 rows)")
    inf_stats = benchmark_inference_only(bundle, n_rows=50)
    print(f"  {_fmt(inf_stats)}")
    inf_ok = inf_stats["median_ms"] < 1000
    print(f"  Target < 1000 ms : {'PASS' if inf_ok else 'NEEDS REVIEW'}")

    # ── Phase 3: End-to-end batch at multiple sizes ────────────────────────
    _section("Phase 3: End-to-end predict_batch() by batch size")
    e2e_results = {}
    for n in BATCH_SIZES:
        s = benchmark_end_to_end_batch(bundle, n_rows=n)
        e2e_results[n] = s
        target_3s = s["median_ms"] < 3000
        print(f"  n={n:>4}  {_fmt(s)}  < 3000 ms: {'PASS' if target_3s else 'NEEDS REVIEW'}")

    # ── Phase 4: Throughput ────────────────────────────────────────────────
    _section("Phase 4: Throughput (records/second)")
    for n, s in e2e_results.items():
        rps = (n / s["median_ms"]) * 1000
        print(f"  n={n:>4}  {rps:.1f} records/s  (median latency)")

    # ── Summary ───────────────────────────────────────────────────────────
    _section("Summary")
    print(f"  Model load      : {load_stats['median_ms']:.2f} ms median")
    print(f"  Preprocessing   : {pre_stats['median_ms']:.2f} ms median (50 rows)")
    print(f"  Inference only  : {inf_stats['median_ms']:.2f} ms median (50 rows)")
    e2e_1  = e2e_results[1]['median_ms']
    e2e_50 = e2e_results[50]['median_ms']
    print(f"  End-to-end n=1  : {e2e_1:.2f} ms median")
    print(f"  End-to-end n=50 : {e2e_50:.2f} ms median")
    print()
    print("  NOTE: All timings are on SYNTHETIC data.")
    print("  Benchmark again after loading real data and on target hardware.")
    print()
    all_ok = (load_stats["median_ms"] < 1000 and
              inf_stats["median_ms"]  < 1000 and
              e2e_results[50]["median_ms"] < 3000)
    print(f"  Overall target check: {'ALL TARGETS MET' if all_ok else 'SOME TARGETS NEED REVIEW'}")


if __name__ == "__main__":
    main()
