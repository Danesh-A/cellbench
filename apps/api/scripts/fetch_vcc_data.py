"""Fetch the Arc Virtual Cell Challenge 2025 dataset into MinIO/S3.

Source: gs://arc-institute-virtual-cell-atlas/virtual-cell-challenge/2025/
License: CC0 1.0
Docs: https://github.com/ArcInstitute/arc-virtual-cell-atlas/blob/main/virtual-cell-challenge/README.md

The new Arc bucket is `Requester Pays`, so the *caller* (you, locally,
or your CI runner) needs Google credentials configured. The simplest
setup is:

    gcloud auth application-default login

Then either run this script directly or let the api container do it on
startup (see `docker-compose.yml`). On a successful run, the following
keys exist in the configured S3/MinIO bucket:

    datasets/vcc-2025/train.h5ad
    datasets/vcc-2025/validation.h5ad
    datasets/vcc-2025/test.h5ad
    eval/vcc-2025/ground_truth.h5ad      (= the test split)
    eval/vcc-2025/basal.h5ad             (control cells from the train split)

The script is idempotent — if all expected objects exist, it does
nothing. Set ``SUBSET_PERTURBATIONS`` in the environment to limit to
the first N perturbations for a faster demo (default: all).
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Iterable

import anndata as ad
import numpy as np

from cellbench_api.config import get_settings
from cellbench_api.storage import ensure_bucket, object_exists, s3_client

log = logging.getLogger("fetch_vcc_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

GCS_BUCKET = "arc-institute-virtual-cell-atlas"
GCS_PREFIX = "virtual-cell-challenge/2025"

# The exact filenames inside Arc's bucket. Verified against the
# arc-virtual-cell-atlas/virtual-cell-challenge README on 2026-05-14.
GCS_FILES = {
    "train": f"{GCS_PREFIX}/train/adata_Training.h5ad",
    "validation": f"{GCS_PREFIX}/validation/adata_Validation.h5ad",
    "test": f"{GCS_PREFIX}/test/adata_Test.h5ad",
}

S3_KEYS = {
    "train": "datasets/vcc-2025/train.h5ad",
    "validation": "datasets/vcc-2025/validation.h5ad",
    "test": "datasets/vcc-2025/test.h5ad",
    "ground_truth": "eval/vcc-2025/ground_truth.h5ad",
    "basal": "eval/vcc-2025/basal.h5ad",
}


def _all_present() -> bool:
    return all(object_exists(k) for k in S3_KEYS.values())


def _download_from_gcs(blob_name: str, dest_path: Path) -> None:
    """Download a blob from the (Requester Pays) Arc bucket.

    Imported lazily so the api container starts even if google-cloud-storage
    is missing — only the fetch path requires it.
    """
    from google.cloud import storage  # type: ignore[import-not-found]

    log.info("gcs_download_start blob=%s dest=%s", blob_name, dest_path)
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET, user_project=client.project)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(str(dest_path))
    log.info("gcs_download_done size_bytes=%d", dest_path.stat().st_size)


def _upload_to_s3(local_path: Path, key: str) -> None:
    settings = get_settings()
    log.info("s3_upload key=%s size_bytes=%d", key, local_path.stat().st_size)
    s3_client().upload_file(str(local_path), settings.s3_bucket, key)


def _subset_perturbations(
    adata: ad.AnnData, n: int, label_col: str = "perturbation"
) -> ad.AnnData:
    """Return adata restricted to the first N distinct perturbations."""
    if label_col not in adata.obs.columns:
        log.warning("subset: obs missing %r — returning full adata", label_col)
        return adata
    labels = adata.obs[label_col].astype(str).to_numpy()
    keep_labels = list(dict.fromkeys(labels))[:n]
    mask = np.isin(labels, keep_labels)
    log.info("subset n_perturbations=%d kept_cells=%d", len(keep_labels), int(mask.sum()))
    return adata[mask].copy()


def _maybe_subset(adata: ad.AnnData) -> ad.AnnData:
    n = int(os.environ.get("SUBSET_PERTURBATIONS", "0") or "0")
    if n <= 0:
        return adata
    return _subset_perturbations(adata, n)


def _derive_basal(train: ad.AnnData) -> ad.AnnData:
    """Extract basal/control cells from the training set.

    The Arc dataset marks control cells with the perturbation label
    ``"non-targeting"`` (CRISPRi non-targeting guides). Fall back to the
    most common label if the convention has shifted.
    """
    if "perturbation" not in train.obs.columns:
        raise RuntimeError("train obs missing 'perturbation' column")
    labels = train.obs["perturbation"].astype(str)
    candidates: Iterable[str] = ("non-targeting", "control", "NT", "ctrl")
    for c in candidates:
        if (labels == c).any():
            return train[labels == c].copy()
    # Fallback: take the most common label as a proxy for control.
    top = labels.value_counts().idxmax()
    log.warning("no explicit control label found; using most-common=%r as basal", top)
    return train[labels == top].copy()


def main() -> None:
    ensure_bucket()
    if _all_present():
        log.info("all_objects_present — nothing to do")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # 1) Download the three splits.
        local_paths: dict[str, Path] = {}
        for split, blob in GCS_FILES.items():
            dst = tmp_path / f"{split}.h5ad"
            if not object_exists(S3_KEYS[split]):
                _download_from_gcs(blob, dst)
                local_paths[split] = dst
            else:
                log.info("skip_download split=%s already in object store", split)

        # 2) Optionally subset, then push the splits to MinIO.
        for split, path in local_paths.items():
            adata = ad.read_h5ad(path)
            adata = _maybe_subset(adata)
            subset_path = tmp_path / f"{split}.subset.h5ad"
            adata.write_h5ad(subset_path)
            _upload_to_s3(subset_path, S3_KEYS[split])

        # 3) Build the eval artefacts:
        #    - ground_truth.h5ad = the test split (with per-cell data + obs.perturbation)
        #    - basal.h5ad        = control cells from the train split
        if not object_exists(S3_KEYS["ground_truth"]):
            test_path = tmp_path / "test.subset.h5ad"
            if test_path.exists():
                _upload_to_s3(test_path, S3_KEYS["ground_truth"])

        if not object_exists(S3_KEYS["basal"]):
            train_path = tmp_path / "train.subset.h5ad"
            if train_path.exists():
                train = ad.read_h5ad(train_path)
                basal = _derive_basal(train)
                basal_path = tmp_path / "basal.h5ad"
                basal.write_h5ad(basal_path)
                _upload_to_s3(basal_path, S3_KEYS["basal"])

    log.info("fetch_complete")


if __name__ == "__main__":
    main()
