import logging

import requests

logger = logging.getLogger(__name__)


def send_webhook(webhook_url, payload, status, key=None):
    """Send a webhook notification with the given payload and status.

    Args:
        webhook_url (str): The webhook endpoint URL
        payload (str): The payload data to send
        status (str): The status string
        key (str, optional): Authorization key for Bearer token authentication

    Returns:
        bool: True if webhook was sent successfully (status code 200), False otherwise
    """
    data = {"payload": payload, "status": status}
    if key:
        data["key"] = key
    try:
        response = requests.post(
            webhook_url, data=data, timeout=10
        )
        if response.status_code == 200:
            return True

        # non-200 response
        logger.error(
            "Webhook returned non-200 status %s for %s; data=%r; response=%r",
            response.status_code,
            webhook_url,
            data,
            # include response text if available
            getattr(response, "text", None),
        )
        return False
    except Exception as e:
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
    data = {}
    if bid is not None:
        data["bid"] = str(bid)
    if schema_id is not None:
        data["schema_id"] = str(schema_id)
    if key:
        data["key"] = key

    try:
        with open(archive_path, "rb") as fh:
            files = {"file": (Path(archive_path).name, fh, "application/x-7z-compressed")}
            resp = requests.post(upload_url, data=data, files=files, timeout=timeout)

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
