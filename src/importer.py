import os
import json
import subprocess
import shutil
import copy
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .logger import get_logger

logger = get_logger(__name__)


class BitwardenImporter:
    def __init__(
        self, data_dir="/data/bitwarden", cache_path="/data/vault_cache.json"
    ):
        self.data_dir = data_dir
        self.cache_path = cache_path
        self.server = os.getenv(
            "BITWARDEN_SERVER", "https://vault.bitwarden.com"
        ).rstrip("/")
        self.client_id = os.getenv("BITWARDEN_CLIENT_ID", "")
        self.client_secret = os.getenv("BITWARDEN_CLIENT_SECRET", "")
        self.mp = os.getenv("BITWARDEN_MP", "")
        self.max_workers = int(os.getenv("IMPORT_WORKERS", "5"))

    def _bw_path(self):
        for p in ["bw", "/usr/local/bin/bw"]:
            if shutil.which(p):
                return p
        return "bw"

    def _run(self, *args, env=None, stdin=None, timeout=120):
        cmd = [self._bw_path(), *args]
        logger.debug("bw: %s", " ".join(str(a) for a in args))

        proc_env = os.environ.copy()
        proc_env["BW_DATA_DIR"] = self.data_dir
        if env:
            proc_env.update(env)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=proc_env,
            timeout=timeout,
            input=stdin,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"bw {' '.join(args)} failed: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def run(self, cache=None):
        if cache is None:
            with open(self.cache_path) as f:
                cache = json.load(f)

        items = cache.get("items", [])
        folders = cache.get("folders", [])

        if not items:
            logger.warning("Cache is empty, nothing to import")
            return {"exported": 0, "imported": 0}

        logger.info("Cache: %d items, %d folders", len(items), len(folders))
        os.makedirs(self.data_dir, exist_ok=True)

        session = None
        try:
            # 1. Configure server
            logger.info("Configuring Bitwarden server: %s", self.server)
            self._run("config", "server", self.server)

            # 2. Login
            logger.info("Logging into Bitwarden cloud...")
            self._run(
                "login",
                "--apikey",
                env={
                    "BW_CLIENTID": self.client_id,
                    "BW_CLIENTSECRET": self.client_secret,
                },
            )

            # 3. Unlock
            logger.debug("Unlocking vault...")
            session = self._unlock()

            # 4. Clear existing vault
            self._clear_vault(session)

            # 5. Recreate folders
            folder_map = self._recreate_folders(session, folders)

            # 6. Import items
            imported = self._import_items(session, items, folder_map)

            return {"exported": len(items), "imported": imported}

        finally:
            try:
                self._run("logout")
            except Exception:
                pass

    def _unlock(self):
        try:
            return self._run("unlock", "--apikey", "--raw")
        except RuntimeError:
            if self.mp:
                logger.debug(
                    "API key unlock failed, trying master password..."
                )
                return self._run(
                    "unlock",
                    "--passwordenv",
                    "BW_PASSWORD",
                    "--raw",
                    env={"BW_PASSWORD": self.mp},
                )
            raise RuntimeError(
                "Failed to unlock Bitwarden vault. "
                "Set BITWARDEN_MP or ensure API key unlock is supported."
            )

    def _clear_vault(self, session):
        logger.info("Clearing existing vault...")

        # Delete items
        items_raw = self._run("list", "items", "--session", session)
        items = json.loads(items_raw)
        if items:
            logger.info("Deleting %d existing items...", len(items))
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = [
                    ex.submit(self._delete_item, item["id"], session)
                    for item in items
                ]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as e:
                        logger.warning("Failed to delete item: %s", e)

        # Delete folders
        folders_raw = self._run("list", "folders", "--session", session)
        folders = json.loads(folders_raw)
        if folders:
            logger.info("Deleting %d existing folders...", len(folders))
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = [
                    ex.submit(self._delete_folder, f["id"], session)
                    for f in folders
                ]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as e:
                        logger.warning("Failed to delete folder: %s", e)

    def _delete_item(self, item_id, session):
        logger.debug("Deleting item: %s", item_id)
        self._run("delete", "item", item_id, "--session", session)

    def _delete_folder(self, folder_id, session):
        logger.debug("Deleting folder: %s", folder_id)
        self._run("delete", "folder", folder_id, "--session", session)

    def _recreate_folders(self, session, folders):
        folder_map = {}
        if not folders:
            return folder_map

        logger.info("Recreating %d folders...", len(folders))
        for folder in folders:
            name = folder.get("name", "Unnamed Folder")
            try:
                raw = self._run(
                    "create", "folder", "--name", name, "--session", session
                )
                created = json.loads(raw)
                folder_map[folder["id"]] = created["id"]
                logger.debug("Folder: %s -> %s", name, created["id"])
            except Exception as e:
                logger.warning("Failed to create folder '%s': %s", name, e)

        return folder_map

    def _import_items(self, session, items, folder_map):
        sanitized = []
        for item in items:
            clean = self._sanitize(item, folder_map)
            if clean:
                sanitized.append(clean)

        total = len(sanitized)
        logger.info(
            "Importing %d items (%d workers)...",
            total,
            self.max_workers,
        )

        imported = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = {
                ex.submit(
                    self._create_item, item, session, idx, total
                ): item.get("name", "Unknown")
                for idx, item in enumerate(sanitized, 1)
            }
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    fut.result()
                    imported += 1
                except Exception as e:
                    logger.warning("Failed to import '%s': %s", name, e)

        logger.info("Imported %d/%d items", imported, total)
        return imported

    def _sanitize(self, item, folder_map):
        clean = copy.deepcopy(item)

        for key in (
            "id",
            "object",
            "organizationId",
            "collectionIds",
            "revisionDate",
            "creationDate",
            "deletedDate",
            "edit",
            "viewPassword",
        ):
            clean.pop(key, None)

        old_fid = item.get("folderId")
        if old_fid and old_fid in folder_map:
            clean["folderId"] = folder_map[old_fid]
        elif old_fid:
            clean["folderId"] = None

        login = clean.get("login")
        if login and login.get("fido2Credentials"):
            for cred in login["fido2Credentials"]:
                cred.pop("id", None)

        return clean

    def _create_item(self, item, session, idx, total):
        name = item.get("name", "Unknown")
        logger.debug("[%d/%d] Creating: %s", idx, total, name)

        payload = json.dumps(item)

        for attempt in range(3):
            try:
                self._run(
                    "create", "item", "--session", session, stdin=payload
                )
                return
            except RuntimeError as e:
                err = str(e).lower()
                if "rate limit" in err or "429" in err or "too many" in err:
                    wait = (2 ** attempt) * 2
                    logger.debug(
                        "Rate limited, waiting %ds (attempt %d/3)...",
                        wait,
                        attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError(f"Failed to create item after 3 attempts: {name}")
