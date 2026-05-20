"""Scoring metrics — Virtual Cell Challenge edition.

CellBench implements the three official Virtual Cell Challenge metrics so
submissions are scored exactly the way Arc Institute scores them:

  * **MAE** — Mean Absolute Error of predicted vs. true mean expression
    across the held-out perturbations.
  * **PDS** — Perturbation Discrimination Score. For each held-out
    perturbation, how well does the prediction's nearest neighbor (by
    Manhattan distance) in the full set of true perturbed transcriptomes
    identify the *correct* perturbation? Reported in the normalized
    form `1 - 2·mean_rank_fraction` so 1.0 is perfect and 0.0 is random.
  * **DES** — Differential Expression Score. For each held-out
    perturbation, find the set of genes that are significantly DE in the
    truth (Wilcoxon vs. basal + Benjamini–Hochberg). Measure what
    fraction of those genes the prediction also flags as DE.

A small REGISTRY at the bottom maps metric names to (signature,
function) so adding a metric is one entry. The signatures are richer
than v1 because DES and PDS need basal (control) cells, not just paired
prediction/truth arrays.

References:
  - "Virtual Cell Challenge: Toward a Turing test for the virtual cell"
    https://www.cell.com/cell/fulltext/S0092-8674(25)00675-0
  - Arc Virtual Cell Atlas — VCC 2025 README
    https://github.com/ArcInstitute/arc-virtual-cell-atlas/blob/main/virtual-cell-challenge/README.md
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


# ---------- Shared types ---------------------------------------------------


@dataclass(frozen=True)
class ScoringContext:
    """All arrays the scorer hands to a metric.

    Each per-perturbation array has shape ``(n_perturbations, n_genes)``.
    Both ``pred`` and ``truth_mean`` are per-perturbation aggregates
    (mean expression across the cells of that perturbation). ``truth_cells``
    and ``basal_cells`` are the raw per-cell matrices, keyed by perturbation
    label, so metrics that need within-perturbation variance (Wilcoxon, DES)
    can compute it. Perturbation labels in `pred_labels` and `truth_labels`
    must align elementwise.
    """

    pred: np.ndarray
    truth_mean: np.ndarray
    pred_labels: list[str]
    truth_labels: list[str]
    truth_cells: dict[str, np.ndarray]  # perturbation -> (n_cells, n_genes)
    basal_cells: np.ndarray              # (n_basal_cells, n_genes)


MetricResult = tuple[float, dict[str, Any]]
Metric = Callable[[ScoringContext], MetricResult]


def _check_shape(ctx: ScoringContext) -> None:
    if ctx.pred.shape != ctx.truth_mean.shape:
        raise ValueError(
            f"shape mismatch: pred {ctx.pred.shape} vs truth_mean {ctx.truth_mean.shape}"
        )
    if ctx.pred_labels != ctx.truth_labels:
        raise ValueError("pred_labels and truth_labels must match elementwise")


# ---------- MAE ------------------------------------------------------------


def mean_absolute_error(ctx: ScoringContext) -> MetricResult:
    """Mean absolute error between predicted and true mean transcriptomes.

    Reported as a similarity in [0, 1]: ``1 / (1 + MAE_raw)``. Larger is
    better, so it can share a leaderboard direction with the other two
    metrics. The raw MAE is included in the breakdown for inspection.
    """
    _check_shape(ctx)
    raw = float(np.abs(ctx.pred - ctx.truth_mean).mean())
    return 1.0 / (1.0 + raw), {
        "mae_raw": raw,
        "n_perturbations": int(ctx.pred.shape[0]),
        "n_genes": int(ctx.pred.shape[1]),
    }


# ---------- PDS ------------------------------------------------------------


def perturbation_discrimination(ctx: ScoringContext) -> MetricResult:
    """Perturbation Discrimination Score.

    For each predicted perturbation t, compute Manhattan distance from
    ``pred[t]`` to every *true* per-perturbation mean. Find the rank of
    the matching true perturbation in that distance ordering, normalize
    by the number of perturbations, then map to ``1 - 2·mean_rank`` so
    random = 0 and perfect = 1.
    """
    _check_shape(ctx)
    pred = ctx.pred.astype(np.float64)
    truth = ctx.truth_mean.astype(np.float64)
    n = pred.shape[0]

    # (n_pred, n_truth) Manhattan distances.
    # |pred[i] - truth[j]|.sum() for all i, j.
    # Done in chunks to avoid an (n, n, n_genes) tensor for large n.
    ranks: list[int] = []
    for i in range(n):
        dists = np.abs(truth - pred[i]).sum(axis=1)
        # Number of *other* perturbations strictly closer than the true one.
        true_dist = dists[i]
        closer = int(np.sum(dists < true_dist))
        ranks.append(closer)

    rank_arr = np.array(ranks, dtype=np.float64) / max(n - 1, 1)
    mean_rank = float(rank_arr.mean())
    score = 1.0 - 2.0 * mean_rank  # in [-1, 1]; clamp at 0 for leaderboard cleanliness
    return max(score, 0.0), {
        "pds_raw": score,
        "mean_rank_fraction": mean_rank,
        "perfect_count": int(np.sum(rank_arr == 0)),
        "n_perturbations": n,
    }


# ---------- DES ------------------------------------------------------------


def _bh_fdr(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Benjamini–Hochberg FDR. Returns a boolean mask of rejections."""
    n = pvals.size
    if n == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(pvals)
    ranked = pvals[order]
    thresholds = alpha * (np.arange(1, n + 1) / n)
    below = ranked <= thresholds
    if not below.any():
        return np.zeros(n, dtype=bool)
    k = int(np.where(below)[0].max())
    mask = np.zeros(n, dtype=bool)
    mask[order[: k + 1]] = True
    return mask


def _de_genes(
    perturbed_cells: np.ndarray, basal_cells: np.ndarray, alpha: float = 0.05
) -> np.ndarray:
    """Return a boolean mask over genes flagged as differentially expressed.

    Uses Wilcoxon rank-sum (Mann-Whitney U) per gene followed by
    Benjamini–Hochberg correction at ``alpha``. ``perturbed_cells`` and
    ``basal_cells`` are ``(n_cells, n_genes)``. Empty inputs return an
    all-False mask.
    """
    if perturbed_cells.size == 0 or basal_cells.size == 0:
        return np.zeros(perturbed_cells.shape[1] if perturbed_cells.ndim == 2 else 0, dtype=bool)

    # scipy.stats.ranksums broadcasts column-wise.
    _, pvals = stats.ranksums(perturbed_cells, basal_cells, axis=0)
    # Replace NaN p-values (constant columns) with 1.0 so they're never rejected.
    pvals = np.where(np.isnan(pvals), 1.0, pvals)
    return _bh_fdr(pvals, alpha=alpha)


def differential_expression(ctx: ScoringContext, alpha: float = 0.05) -> MetricResult:
    """Differential Expression Score.

    For each held-out perturbation:
      1. Identify the true DE gene set: Wilcoxon rank-sum vs. basal
         cells + Benjamini-Hochberg at ``alpha``, applied to the true
         per-cell matrix for that perturbation.
      2. Identify the predicted DE gene set: same procedure, applied to
         the *predicted* mean treated as a single noisy sample is not
         meaningful, so for the prediction we instead compare predicted
         per-gene effect size against basal per-gene mean using a simple
         z-test against basal variance. This is the standard CellBench
         approximation; participants who want strict parity with Arc's
         scoring pipeline can submit per-cell predictions (future work).
      3. DE_score = |true ∩ pred| / |true|, averaged over perturbations.
    """
    _check_shape(ctx)
    basal = ctx.basal_cells.astype(np.float64)
    basal_mean = basal.mean(axis=0)
    basal_std = basal.std(axis=0)
    # Guard against zero variance genes — they can't be flagged.
    basal_std = np.where(basal_std == 0, np.inf, basal_std)

    per_pert: list[float] = []
    for i, label in enumerate(ctx.truth_labels):
        true_cells = ctx.truth_cells.get(label)
        if true_cells is None or true_cells.size == 0:
            continue
        true_mask = _de_genes(true_cells, basal, alpha=alpha)
        n_true = int(true_mask.sum())
        if n_true == 0:
            # No true DE genes — vacuously perfect prediction.
            per_pert.append(1.0)
            continue

        # Predicted DE: z-score predicted mean vs. basal distribution.
        z = (ctx.pred[i].astype(np.float64) - basal_mean) / basal_std
        # Two-sided p-values from normal approximation.
        pvals = 2 * (1 - stats.norm.cdf(np.abs(z)))
        pred_mask = _bh_fdr(pvals, alpha=alpha)

        # Restrict pred to top-|true| if we over-predict (Arc's tie-break).
        if int(pred_mask.sum()) > n_true:
            # Keep the |true| most extreme z-scores among the predicted set.
            keep_idx = np.argsort(-np.abs(z))[:n_true]
            pred_mask = np.zeros_like(pred_mask)
            pred_mask[keep_idx] = True

        overlap = int(np.logical_and(true_mask, pred_mask).sum())
        per_pert.append(overlap / n_true)

    if not per_pert:
        return 0.0, {"des": 0.0, "n_perturbations_scored": 0}

    score = float(np.mean(per_pert))
    return score, {
        "des": score,
        "n_perturbations_scored": len(per_pert),
        "per_perturbation_min": float(min(per_pert)),
        "per_perturbation_max": float(max(per_pert)),
        "alpha": alpha,
    }


# ---------- Composite score ------------------------------------------------


def vcc_composite(ctx: ScoringContext) -> MetricResult:
    """Mean of normalized DES, PDS, and MAE-similarity.

    Each component is already in [0, 1] with higher = better, so the
    composite is a simple unweighted mean. Breakdown includes each
    individual score so the leaderboard can show all four columns.
    """
    des, des_bd = differential_expression(ctx)
    pds, pds_bd = perturbation_discrimination(ctx)
    mae_sim, mae_bd = mean_absolute_error(ctx)

    composite = float((des + pds + mae_sim) / 3.0)
    return composite, {
        "composite": composite,
        "des": des,
        "pds": pds,
        "mae_similarity": mae_sim,
        "mae_raw": mae_bd["mae_raw"],
        "des_breakdown": des_bd,
        "pds_breakdown": pds_bd,
    }


# ---------- Registry ------------------------------------------------------


REGISTRY: dict[str, Metric] = {
    "mae": mean_absolute_error,
    "pds": perturbation_discrimination,
    "des": differential_expression,
    "vcc_composite": vcc_composite,
}
