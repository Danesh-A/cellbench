"""S3-compatible object storage client.

The API process never streams large files; it mints time-limited
pre-signed URLs for clients (and the scorer worker) to use directly.
"""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.client import Config

from cellbench_api.config import get_settings


@lru_cache
def s3_client():  # type: ignore[no-untyped-def]
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    """Create the bucket on startup if it doesn't exist. Idempotent."""
    settings = get_settings()
    client = s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        client.create_bucket(Bucket=settings.s3_bucket)


def presign_put(key: str, content_type: str = "application/octet-stream") -> str:
    settings = get_settings()
    return s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.presigned_url_ttl,
    )


def presign_get(key: str) -> str:
    settings = get_settings()
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.presigned_url_ttl,
    )


def object_exists(key: str) -> bool:
    settings = get_settings()
    try:
        s3_client().head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except Exception:
        return False
