import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .logger import get_logger

logger = get_logger(__name__)

BULK_DELETE_CHUNK_SIZE = 500
REQUEST_TIMEOUT_SECONDS = 60
DEVICE_TYPE_LINUX_CLI = 25
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class _TransientApiError(Exception):
    pass


class BitwardenApiClient:
    def __init__(
        self,
        server,
        client_id,
        client_secret,
        client_version,
        device_id_path,
    ):
        self.server = server.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.client_version = client_version
        self.device_id_path = device_id_path
        self.access_token = None

    def clear_vault(self):
        self._authenticate()
        vault = self._request_json("GET", "/api/sync")

        items = vault.get("ciphers", [])
        folders = vault.get("folders", [])

        if items:
            logger.info(
                "Permanently deleting %d items via the Bitwarden API...",
                len(items),
            )
            self._delete_many("/api/ciphers", [item["id"] for item in items])
        else:
            logger.info("Existing vault has no items to delete")

        if folders:
            logger.info(
                "Permanently deleting %d folders via the Bitwarden API...",
                len(folders),
            )
            self._delete_many("/api/folders", [folder["id"] for folder in folders])

        return {"item_count": len(items), "folder_count": len(folders)}

    def _authenticate(self):
        token_body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "scope": "api",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "deviceType": str(DEVICE_TYPE_LINUX_CLI),
                "deviceIdentifier": self._device_id(),
                "deviceName": "Linux CLI",
            }
        ).encode("utf-8")

        token_response = self._request_json(
            "POST",
            "/identity/connect/token",
            body=token_body,
            content_type="application/x-www-form-urlencoded",
        )
        self.access_token = token_response.get("access_token")
        if not self.access_token:
            raise RuntimeError(
                "Bitwarden API authentication returned no access token"
            )

    def _device_id(self):
        try:
            with open(self.device_id_path, encoding="utf-8") as device_file:
                device_id = device_file.read().strip()
            if device_id:
                return device_id
        except FileNotFoundError:
            pass

        device_id = str(uuid.uuid4())
        device_directory = os.path.dirname(self.device_id_path)
        if device_directory:
            os.makedirs(device_directory, exist_ok=True)
        with open(self.device_id_path, "w", encoding="utf-8") as device_file:
            device_file.write(device_id)
        return device_id

    def _delete_many(self, path, ids):
        for start_index in range(0, len(ids), BULK_DELETE_CHUNK_SIZE):
            chunk = ids[start_index : start_index + BULK_DELETE_CHUNK_SIZE]
            self._request_json("DELETE", path, payload={"ids": chunk})

    def _request_json(
        self,
        method,
        path,
        payload=None,
        body=None,
        content_type=None,
        max_attempts=4,
        initial_delay=2,
    ):
        for attempt in range(1, max_attempts + 1):
            try:
                return self._request_once(
                    method,
                    path,
                    payload=payload,
                    body=body,
                    content_type=content_type,
                )
            except _TransientApiError as error:
                if attempt == max_attempts:
                    raise RuntimeError(str(error)) from None
                delay_seconds = min(initial_delay * 2 ** (attempt - 1), 30)
                logger.warning(
                    "Bitwarden API request failed transiently on attempt %d of %d; "
                    "retrying in %d seconds: %s",
                    attempt,
                    max_attempts,
                    delay_seconds,
                    error,
                )
                time.sleep(delay_seconds)

    def _request_once(self, method, path, payload=None, body=None, content_type=None):
        headers = {
            "Accept": "application/json",
            "Device-Type": str(DEVICE_TYPE_LINUX_CLI),
            "Bitwarden-Client-Version": self.client_version,
        }

        request_body = body
        if payload is not None:
            request_body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif content_type:
            headers["Content-Type"] = content_type

        if self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token

        request = urllib.request.Request(
            self.server + path,
            data=request_body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            message = (
                f"Bitwarden API request failed with status {error.code}: "
                f"{error_body[:500]}"
            )
            if error.code in TRANSIENT_STATUS_CODES:
                raise _TransientApiError(message) from None
            raise RuntimeError(message) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise _TransientApiError(
                f"Bitwarden API request failed: {error}"
            ) from None
