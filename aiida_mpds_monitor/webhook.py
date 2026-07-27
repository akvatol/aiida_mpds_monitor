import logging
from pathlib import Path, PurePosixPath

import py7zr
import requests

logger = logging.getLogger(__name__)

REQUIRED_OUTPUT_TYPES = frozenset({"STRUCT", "PHONON", "ELASTIC"})


def validate_archive_outputs(archive_path: str | Path) -> bool:
    """Check that an archive has one OUTPUT file for every required calculation type."""
    archive_path = Path(archive_path)

    try:
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            output_paths = [
                PurePosixPath(name)
                for name in archive.getnames()
                if PurePosixPath(name).name == "OUTPUT"
            ]
    except Exception as exc:
        logger.error("Could not inspect archive %s: %s", archive_path, exc)
        return False

    output_types = {
        path.parts[-2]
        for path in output_paths
        if len(path.parts) >= 2
    }
    missing_types = REQUIRED_OUTPUT_TYPES - output_types

    if len(output_paths) != len(REQUIRED_OUTPUT_TYPES) or missing_types:
        logger.error(
            "Archive %s was not uploaded: expected exactly three OUTPUT files "
            "(one in each of %s); found %s",
            archive_path,
            ", ".join(sorted(REQUIRED_OUTPUT_TYPES)),
            ", ".join(str(path) for path in output_paths) or "none",
        )
        return False

    return True


def send_webhook(webhook_url, payload, status, key=None):
    """Send a webhook notification with the given payload and status.

    Args:
        webhook_url (str): The webhook endpoint URL
        payload (str): The payload data to send
        status (str): The status string
        key (str, optional): Authorization key for Bearer token authentication

    Returns:
        bool: True if webhook was sent successfully (200) or already exists on server (409), False otherwise
    """
    data = {"payload": payload, "status": status}
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = requests.post(
            webhook_url, data=data, headers=headers or None, timeout=10
        )
        if response.status_code == 200:
            return True

        data["key"] = "***"

        if response.status_code == 409:
            logger.info(
                "Webhook returned 409 for %s (already exists on server) — marking as done; data=%r",
                webhook_url,
                data,
            )
            return True

        # non-200/non-409 response
        logger.error(
            "Webhook returned non-200 status %s for %s; data=%r; response=%r",
            response.status_code,
            webhook_url,
            data,
            getattr(response, "text", None),
        )
        return False
    except Exception as e:

        data["key"] = "***"

        logger.error(
            "Webhook error: %s (url=%s, data=%r)",
            e,
            webhook_url,
            data,
        )
        return False


def send_archive(upload_url, archive_path, bid: int | None = None, schema_id: int | None = None, key: str | None = None, timeout: int = 30):
    """
    Upload a 7z archive file to the given `upload_url` endpoint using multipart/form-data.

    Args:
        upload_url (str): Full URL to POST the archive to (e.g. https://host/upload/absolidix)
        archive_path (str or Path): Path to the archive file to upload
        bid (int, optional): Optional `bid` form field
        schema_id (int, optional): Optional `schema_id` form field
        key (str, optional): Optional auth key included in form data as `key`
        timeout (int): request timeout in seconds

    Returns:
        bool: True if upload returned HTTP 200, False otherwise
    """
    if not validate_archive_outputs(archive_path):
        return False

    data = {}
    if bid is not None:
        data["bid"] = str(bid)
    if schema_id is not None:
        data["schema_id"] = str(schema_id)

    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        with open(archive_path, "rb") as fh:
            files = {"file": (Path(archive_path).name, fh, "application/x-7z-compressed")}
            resp = requests.post(
                upload_url,
                data=data,
                files=files,
                headers=headers or None,
                timeout=timeout,
            )

        if resp.status_code == 200:
            return True

        logger.error(
            "Archive upload returned non-200 status %s for %s; data=%r; response=%r",
            resp.status_code,
            upload_url,
            data,
            getattr(resp, "text", None),
        )
        return False
    except Exception as e:
        logger.error("Archive upload error: %s (url=%s, data=%r)", e, upload_url, data)
        return False
