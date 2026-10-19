import os
import json
import time

from .bitwarden_api import BitwardenApiClient
from .bw_cli import BitwardenCli
from .logger import get_logger

logger = get_logger(__name__)

# Bitwarden Cloud limits how quickly one user can modify the vault, and every
# Bitwarden CLI process shares the same data directory, so deletes run one at
# a time with a pause between them instead of in parallel.
DELETE_DELAY_SECONDS = 0.5
MAX_CLEAR_VERIFICATION_ROUNDS = 3


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
                # The CLI lists items from its local cache, and the import
                # command does not wait for its own background sync to finish,
                # so refresh the cache before every count.
                self._sync(session)
                visible_listing = self._run_with_retry(
                    "list", "items", "--session", session
                )
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
                if attempt < 5:
                    time.sleep(15)

            if imported_count != expected_visible:
                raise RuntimeError(
                    f"Import verification failed: expected {expected_visible} "
                    f"visible items but found {imported_count} in the Bitwarden vault"
                )
            logger.info(
                "Import verified: %d/%d visible items present in Bitwarden",
                imported_count,
                expected_visible,
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

    def _sync(self, session):
        logger.debug("Refreshing the local vault cache from the Bitwarden server...")
        self._run_with_retry("sync", "--force", "--session", session, timeout=300)

    def _export_snapshot(self, session):
        snapshot_path = "/data/clear_snapshot.json"
        try:
            self._run_with_retry(
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
                return json.load(snapshot_file)
        finally:
            # The snapshot is plaintext, including archived items
            try:
                os.remove(snapshot_path)
            except FileNotFoundError:
                pass

    def _clear_vault(self, session):
        logger.info("Clearing existing vault...")

        try:
            self._clear_vault_via_api()
        except Exception as error:
            logger.warning(
                "Bulk API clear failed; falling back to per-item CLI deletion: %s",
                error,
            )
            self._clear_vault_via_cli(session)

        self._verify_vault_is_empty(session)

    def _clear_vault_via_api(self):
        api_client = BitwardenApiClient(
            server=self.server,
            client_id=self.client_id,
            client_secret=self.client_secret,
            client_version=self._run("--version"),
            device_id_path="/data/bitwarden_device_id",
        )
        api_client.clear_vault()

    def _clear_vault_via_cli(self, session):
        # Refresh after a partial API clear so the snapshot does not contain
        # IDs that are already gone from the server.
        self._sync(session)

        # List filters cannot be trusted for clearing: the plain list hides
        # archived items and the --archived filter is unreliable in CLI 2026.x,
        # so the vault is enumerated through a throwaway export instead, which
        # reports every item including archived ones.
        snapshot = self._export_snapshot(session)
        items = snapshot.get("items", [])
        folders = snapshot.get("folders", [])

        if items:
            logger.info("Permanently deleting %d existing items...", len(items))
            self._delete_items(items, session)
        else:
            logger.info("Existing vault has no items to delete")

        # Exports exclude trashed ciphers, so the trash is listed separately.
        # The list comes from the local cache, so sync before reading it.
        self._sync(session)
        trashed_items = json.loads(
            self._run_with_retry("list", "items", "--trash", "--session", session)
        )
        if trashed_items:
            logger.info("Permanently deleting %d trashed items...", len(trashed_items))
            self._delete_items(trashed_items, session)

        if folders:
            logger.info("Permanently deleting %d existing folders...", len(folders))
            self._delete_folders(folders, session)

    def _verify_vault_is_empty(self, session):
        logger.info("Verifying the Bitwarden vault is empty...")

        for verification_round in range(1, MAX_CLEAR_VERIFICATION_ROUNDS + 1):
            self._sync(session)
            snapshot = self._export_snapshot(session)
            remaining_items = snapshot.get("items", [])
            remaining_folders = snapshot.get("folders", [])
            trashed_items = json.loads(
                self._run_with_retry("list", "items", "--trash", "--session", session)
            )

            if not remaining_items and not remaining_folders and not trashed_items:
                logger.info("Clear verified: the Bitwarden vault is empty")
                return

            logger.warning(
                "Clear verification round %d of %d found %d items, %d folders, "
                "and %d trashed items remaining",
                verification_round,
                MAX_CLEAR_VERIFICATION_ROUNDS,
                len(remaining_items),
                len(remaining_folders),
                len(trashed_items),
            )
            if verification_round == MAX_CLEAR_VERIFICATION_ROUNDS:
                break

            if remaining_items:
                self._delete_items(remaining_items, session)
            if trashed_items:
                self._delete_items(trashed_items, session)
            if remaining_folders:
                self._delete_folders(remaining_folders, session)

            wait_seconds = 15 * verification_round
            logger.info("Retrying clear verification in %d seconds...", wait_seconds)
            time.sleep(wait_seconds)

        raise RuntimeError(
            "Clear verification failed: the Bitwarden vault still contains "
            "items after retrying deletions"
        )

    def _delete_items(self, items, session):
        for item in items:
            try:
                self._delete_item(item["id"], session)
            except RuntimeError as error:
                # A stale snapshot can list items that are already gone
                if "not found" not in str(error).lower():
                    logger.warning("Failed to permanently delete item: %s", error)
            time.sleep(DELETE_DELAY_SECONDS)

    def _delete_folders(self, folders, session):
        for folder in folders:
            try:
                self._delete_folder(folder["id"], session)
            except RuntimeError as error:
                # Stale folder listings are common right after bulk deletes
                if "not found" not in str(error).lower():
                    logger.warning("Failed to permanently delete folder: %s", error)
            time.sleep(DELETE_DELAY_SECONDS)

    def _delete_item(self, item_id, session):
        logger.debug("Deleting item: %s", item_id)
        # Permanent delete keeps the cloud Trash from filling up on every sync
        self._run_with_retry(
            "delete",
            "item",
            item_id,
            "--permanent",
            "--session",
            session,
            timeout=60,
        )

    def _delete_folder(self, folder_id, session):
        logger.debug("Deleting folder: %s", folder_id)
        self._run_with_retry(
            "delete",
            "folder",
            folder_id,
            "--permanent",
            "--session",
            session,
            timeout=60,
        )
