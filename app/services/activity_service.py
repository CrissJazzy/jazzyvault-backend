import logging

from app.db.supabase_client import get_supabase_admin

logger = logging.getLogger(__name__)

# Mirrors the activity_logs.activity_type CHECK constraint in
# supabase/migrations/004_activity_logs.sql — keep these in sync.
ACTIVITY_TYPES = {
    "file_upload",
    "file_delete",
    "file_download",
    "conversion_started",
    "conversion_completed",
    "conversion_failed",
    "ai_request",
}


class ActivityService:
    @staticmethod
    def log(
        user_id: str,
        activity_type: str,
        description: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Writes an activity_logs row. Deliberately fire-and-forget: a
        logging failure should never break the underlying operation
        (an upload that succeeds shouldn't 500 because the activity
        feed write failed), so all errors are caught and logged rather
        than raised.
        """
        if activity_type not in ACTIVITY_TYPES:
            logger.warning("Unknown activity_type '%s' — skipping log.", activity_type)
            return

        try:
            admin = get_supabase_admin()
            admin.table("activity_logs").insert(
                {
                    "user_id": user_id,
                    "activity_type": activity_type,
                    "description": description,
                    "metadata": metadata or {},
                }
            ).execute()
        except Exception:
            logger.exception("Failed to write activity log (non-fatal)")
