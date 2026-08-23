import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .bw_cli import BitwardenCli
from .logger import get_logger

logger = get_logger(__name__)


class BitwardenImporter(BitwardenCli):
    def __init__(self):
        super().__init__(data_dir="/data/bitwarden")
        self.server = os.getenv(
            "BITWARDEN_SERVER", "https://vault.bitwarden.com"
        ).rstrip("/")
        self.client_id = os.getenv("BITWARDEN_CLIENT_ID", "")
        self.client_secret = os.getenv("BITWARDEN_CLIENT_SECRET", "")
        self.master_password = os.getenv("BITWARDEN_MP", "")

    def run(self, export_path):
        with open(export_path, encoding="utf-8") as export_file:
            exported_vault = json.load(export_file)

        expected_items = len(exported_vault.get("items", []))
        expected_folders = len(exported_vault.get("folders", []))
        logger.info(
            "Loaded export: %d items, %d folders",
            expected_items,
            expected_folders,
        )

        try:
            # 1. Configure server
            logger.info("Configuring Bitwarden server: %s", self.server)
            self._run("config", "server", self.server)

            # 2. Login (API key authenticates identity only)
            logger.info("Logging into Bitwarden cloud...")
            self._run(
                "login",
                "--apikey",
                extra_environment={
                    "BW_CLIENTID": self.client_id,
                    "BW_CLIENTSECRET": self.client_secret,
                },
            )

            # 3. Unlock (decryption always requires the master password)
            logger.debug("Unlocking vault...")
            session = self._run(
                "unlock",
                "--passwordenv",
                "BW_PASSWORD",
                "--raw",
                extra_environment={"BW_PASSWORD": self.master_password},
            )

            # 4. Clear existing vault (import merges, it never replaces)
            self._clear_vault(session)

            # 5. Import the whole vault in a single native call;
            #    the bitwardenjson importer rebuilds folders and remaps references itself
            logger.info(
                "Importing %d items via Bitwarden CLI import...",
                expected_items,
            )
            self._run(
                "import",
                "bitwardenjson",
                export_path,
                "--session",
                session,
                timeout=1800,
            )

            # 6. Verify the target vault matches the export before declaring success.
            # The plain item list is the only reliable count: the --archived
            # filter is unreliable in CLI 2026.x and can return every item, so
            # expected visibility is derived from the export instead. Archived
            # items are hidden from the plain list, hence subtracted here.
            expected_visible = expected_items - len(
                [
                    item
                    for item in exported_vault.get("items", [])
                    if item.get("archivedDate")
                ]
            )
            imported_count = None
            for attempt in range(1, 6):
                visible_listing = self._run("list", "items", "--session", session)
                imported_count = len(json.loads(visible_listing))
                if imported_count == expected_visible:
                    break
                logger.info(
                    "Verification attempt %d of 5 found %d of %d visible items; "
                    "waiting 15 seconds before retrying...",
                    attempt,
                    imported_count,
                    expected_visible,
                )
                time.sleep(15)

            if imported_count != expected_visible:
                raise RuntimeError(
                    f"Import verification failed: expected {expected_visible} "
                    f"visible items but found {imported_count} in the Bitwarden vault"
                )
            logger.info(
                "Import verified: %d/%d items present in Bitwarden",
                expected_items,
                expected_items,
            )

            return {"imported_count": imported_count}

        finally:
            # The export file is plaintext; never leave it on disk after the cycle
            try:
                os.remove(export_path)
            except FileNotFoundError:
                pass

            try:
                self._run("logout")
            except Exception:
                pass

    def _clear_vault(self, session):
        logger.info("Clearing existing vault...")

        # List filters cannot be trusted for clearing: the plain list hides
        # archived items and the --archived filter is unreliable in CLI 2026.x,
        # so the vault is enumerated through a throwaway export instead, which
        # reports every item including archived ones.
        snapshot_path = "/data/clear_snapshot.json"
        self._run(
            "export",
            "--format",
            "json",
            "--output",
            snapshot_path,
            "--session",
            session,
            timeout=600,
        )
        with open(snapshot_path, encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)
        os.remove(snapshot_path)

        items = snapshot.get("items", [])
        if items:
            logger.info("Permanently deleting %d existing items...", len(items))
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(self._delete_item, item["id"], session)
                    for item in items
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except RuntimeError as error:
                        # An item already gone (stale snapshot) counts as cleared
                        if "not found" in str(error).lower():
                            continue
                        logger.warning("Failed to delete item: %s", error)
                    except Exception as error:
                        logger.warning("Failed to delete item: %s", error)
        else:
            logger.info("Existing vault has no items to delete")

        # Exports exclude trashed ciphers, so the trash is listed separately;
        # permanent deletes keep it empty instead of accumulating ~400 per day
        trashed_items = json.loads(
            self._run("list", "items", "--trash", "--session", session)
        )
        if trashed_items:
            logger.info(
                "Permanently deleting %d trashed items...", len(trashed_items)
            )
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(self._delete_item, item["id"], session)
                    for item in trashed_items
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as error:
                        logger.warning("Failed to delete trashed item: %s", error)

        folders = snapshot.get("folders", [])
        if folders:
            logger.info("Permanently deleting %d existing folders...", len(folders))
            for folder in folders:
                try:
                    self._delete_folder(folder["id"], session)
                except RuntimeError as error:
                    # Stale folder listings are common right after bulk deletes
                    if "not found" in str(error).lower():
                        continue
                    logger.warning("Failed to delete folder: %s", error)
                except Exception as error:
                    logger.warning("Failed to delete folder: %s", error)

    def _delete_item(self, item_id, session):
        logger.debug("Deleting item: %s", item_id)
        # Permanent delete keeps the cloud Trash from filling up on every sync
        self._run("delete", "item", item_id, "--permanent", "--session", session)

    def _delete_folder(self, folder_id, session):
        logger.debug("Deleting folder: %s", folder_id)
        self._run("delete", "folder", folder_id, "--permanent", "--session", session)
