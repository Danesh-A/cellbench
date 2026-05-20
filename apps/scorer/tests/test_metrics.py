"""Unit tests for the three official VCC scoring metrics.

Where exact correctness against Arc's reference scorer would require
their full pipeline, we test the *properties* that any correct
implementation must satisfy: bounds, monotonicity, symmetry, and
behavior at the perfect / random ends of the spectrum.
"""

from __future__ import annotations

import numpy as np
import pytest

from cellbench_scorer.metrics import (
    ScoringContext,
    differential_expression,
    mean_absolute_error,
    perturbation_discrimination,
    vcc_composite,
)


# ---------- fixtures -------------------------------------------------------


def _make_ctx(
    seed: int = 0,
    n_perturbations: int = 8,
    n_genes: int = 100,
    n_cells_per_pert: int = 30,
    n_basal: int = 50,
    perfect: bool = False,
    random: bool = False,
) -> ScoringContext:
    """Build a synthetic ScoringContext with known structure.

    Each perturbation gets a distinctive shift on a different subset of
    genes against the basal mean; `perfect=True` makes pred==truth_mean,
    `random=True` replaces pred with independent noise.
    """
    rng = np.random.RandomState(seed)
    basal = rng.normal(loc=5.0, scale=1.0, size=(n_basal, n_genes))
    basal_mean = basal.mean(axis=0)

    labels = [f"P{i:02d}" for i in range(n_perturbations)]
    truth_cells: dict[str, np.ndarray] = {}
    truth_mean = np.zeros((n_perturbations, n_genes))

    for i, lbl in enumerate(labels):
        # Each perturbation hits a distinct gene with a large negative shift.
        cells = rng.normal(loc=5.0, scale=1.0, size=(n_cells_per_pert, n_genes))
        cells[:, i % n_genes] -= 5.0  # huge knockdown of one gene
        truth_cells[lbl] = cells
        truth_mean[i] = cells.mean(axis=0)

    if perfect:
        pred = truth_mean.copy()
    elif random:
        pred = rng.normal(loc=basal_mean.mean(), scale=1.0, size=truth_mean.shape)
    else:
        # Slightly noised but mostly correct.
        pred = truth_mean + rng.normal(scale=0.1, size=truth_mean.shape)

    return ScoringContext(
        pred=pred,
        truth_mean=truth_mean,
        pred_labels=list(labels),
        truth_labels=list(labels),
        truth_cells=truth_cells,
        basal_cells=basal,
    )


# ---------- MAE ------------------------------------------------------------


def test_mae_perfect_is_one() -> None:
    ctx = _make_ctx(perfect=True)
    score, bd = mean_absolute_error(ctx)
    assert score == pytest.approx(1.0)
    assert bd["mae_raw"] == pytest.approx(0.0)


def test_mae_random_is_less_than_perfect() -> None:
    perfect = mean_absolute_error(_make_ctx(perfect=True))[0]
    random = mean_absolute_error(_make_ctx(random=True))[0]
    assert random < perfect


def test_mae_shape_mismatch_raises() -> None:
    rng = np.random.RandomState(0)
    bad = ScoringContext(
        pred=np.zeros((3, 4)),
        truth_mean=np.zeros((3, 5)),
        pred_labels=["a", "b", "c"],
        truth_labels=["a", "b", "c"],
        truth_cells={},
        basal_cells=rng.normal(size=(10, 5)),
    )
    with pytest.raises(ValueError):
        mean_absolute_error(bad)


# ---------- PDS ------------------------------------------------------------


def test_pds_perfect_is_one() -> None:
    ctx = _make_ctx(perfect=True)
    score, bd = perturbation_discrimination(ctx)
    assert score == pytest.approx(1.0)
    assert bd["perfect_count"] == ctx.pred.shape[0]


def test_pds_random_near_zero() -> None:
    # Average over a few seeds to denoise.
    scores = [perturbation_discrimination(_make_ctx(seed=s, random=True))[0] for s in range(5)]
    assert np.mean(scores) < 0.3


def test_pds_good_predictions_beat_random() -> None:
    good = perturbation_discrimination(_make_ctx(seed=0, perfect=False))[0]
    rand = perturbation_discrimination(_make_ctx(seed=0, random=True))[0]
    assert good > rand


# ---------- DES ------------------------------------------------------------


def test_des_perfect_predictions_recover_de_genes() -> None:
    # When pred is the true per-perturbation mean, the per-gene z-score
    # against basal is large at exactly the knocked-down gene, so we
    # should recover a meaningful fraction of DE genes.
    ctx = _make_ctx(seed=0, perfect=True, n_cells_per_pert=50, n_basal=100)
    score, bd = differential_expression(ctx)
    # Each perturbation has a single huge effect; correct recovery
    # should give a score well above random.
    assert score > 0.5, f"got DES={score}, expected > 0.5"
    assert bd["n_perturbations_scored"] == ctx.pred.shape[0]


def test_des_random_is_low() -> None:
    ctx = _make_ctx(seed=0, random=True, n_cells_per_pert=50, n_basal=100)
    score, _ = differential_expression(ctx)
    assert score < 0.5


# ---------- Composite ------------------------------------------------------


def test_composite_breakdown_includes_all_three() -> None:
    score, bd = vcc_composite(_make_ctx(perfect=True))
    assert set(bd.keys()) >= {"composite", "des", "pds", "mae_similarity"}
    assert bd["pds"] == pytest.approx(1.0)
    assert bd["mae_similarity"] == pytest.approx(1.0)
    assert score == pytest.approx((bd["des"] + bd["pds"] + bd["mae_similarity"]) / 3.0)
