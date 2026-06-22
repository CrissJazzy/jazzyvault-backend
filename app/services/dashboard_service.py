from app.db.supabase_client import get_supabase_admin
from app.schemas.dashboard import (
    ActivityFeedResponse,
    ActivityLogEntry,
    DashboardStats,
    GlobalSearchResponse,
    SearchResultType,
)


class DashboardService:
    @staticmethod
    def get_stats(user_id: str) -> DashboardStats:
        admin = get_supabase_admin()

        # Supabase's count="exact" with head=True returns just the row
        # count without fetching data — cheap even as history grows.
        total_files = (
            admin.table("files")
            .select("id", count="exact", head=True)
            .eq("user_id", user_id)
            .execute()
        ).count or 0

        total_conversions = (
            admin.table("conversions")
            .select("id", count="exact", head=True)
            .eq("user_id", user_id)
            .execute()
        ).count or 0

        successful_conversions = (
            admin.table("conversions")
            .select("id", count="exact", head=True)
            .eq("user_id", user_id)
            .eq("status", "completed")
            .execute()
        ).count or 0

        failed_conversions = (
            admin.table("conversions")
            .select("id", count="exact", head=True)
            .eq("user_id", user_id)
            .eq("status", "failed")
            .execute()
        ).count or 0

        profile = (
            admin.table("profiles")
            .select("storage_used_bytes, storage_limit_bytes")
            .eq("id", user_id)
            .single()
            .execute()
        )
        storage_used = profile.data.get("storage_used_bytes", 0) if profile.data else 0
        storage_limit = (
            profile.data.get("storage_limit_bytes", 1073741824) if profile.data else 1073741824
        )

        return DashboardStats(
            total_files=total_files,
            total_conversions=total_conversions,
            successful_conversions=successful_conversions,
            failed_conversions=failed_conversions,
            storage_used_bytes=storage_used,
            storage_limit_bytes=storage_limit,
        )

    @staticmethod
    def get_recent_activity(user_id: str, limit: int = 20) -> ActivityFeedResponse:
        admin = get_supabase_admin()
        result = (
            admin.table("activity_logs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        activities = [ActivityLogEntry(**row) for row in result.data]
        return ActivityFeedResponse(activities=activities, total=len(activities))

    @staticmethod
    def global_search(user_id: str, query: str, limit_per_type: int = 8) -> GlobalSearchResponse:
        """
        Searches across files (by name), conversions (by joined source
        file name), and AI requests (by joined source file name + request
        type), merging results by recency. Three small queries rather than
        one complex cross-table query — simpler to reason about and each
        query stays fast since it's scoped to a single user.
        """
        admin = get_supabase_admin()
        results: list[SearchResultType] = []

        # --- Files ---
        files_result = (
            admin.table("files")
            .select("id, file_name, file_type, created_at")
            .eq("user_id", user_id)
            .ilike("file_name", f"%{query}%")
            .order("created_at", desc=True)
            .limit(limit_per_type)
            .execute()
        )
        for row in files_result.data:
            results.append(
                SearchResultType(
                    type="file",
                    id=row["id"],
                    title=row["file_name"],
                    subtitle=f"{row['file_type'].upper()} file",
                    created_at=row["created_at"],
                    link="/files",
                )
            )

        # --- Conversions (search by the source file's name, via join) ---
        conversions_result = (
            admin.table("conversions")
            .select(
                "id, input_format, output_format, status, created_at, "
                "input_file:files!conversions_input_file_fkey(file_name)"
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(50)  # filtered client-side below, same pattern as /convert/history
            .execute()
        )
        needle = query.lower()
        matched_conversions = [
            row
            for row in conversions_result.data
            if row.get("input_file")
            and needle in (row["input_file"].get("file_name") or "").lower()
        ][:limit_per_type]
        for row in matched_conversions:
            file_name = row["input_file"]["file_name"]
            results.append(
                SearchResultType(
                    type="conversion",
                    id=row["id"],
                    title=file_name,
                    subtitle=f"{row['input_format'].upper()} \u2192 {row['output_format'].upper()} \u2022 {row['status']}",
                    created_at=row["created_at"],
                    link="/conversions",
                )
            )

        # --- AI requests (search by source file name + request type) ---
        ai_result = (
            admin.table("ai_requests")
            .select(
                "id, request_type, status, created_at, "
                "file:files(file_name)"
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        matched_ai = [
            row
            for row in ai_result.data
            if (row.get("file") and needle in (row["file"].get("file_name") or "").lower())
            or needle in row["request_type"].lower()
        ][:limit_per_type]
        for row in matched_ai:
            file_name = row["file"]["file_name"] if row.get("file") else "Unknown file"
            results.append(
                SearchResultType(
                    type="ai_request",
                    id=row["id"],
                    title=file_name,
                    subtitle=f"{row['request_type'].capitalize()} \u2022 {row['status']}",
                    created_at=row["created_at"],
                    link="/ai-tools",
                )
            )

        # Merge by recency across all three types.
        results.sort(key=lambda r: r.created_at, reverse=True)
        return GlobalSearchResponse(results=results, total=len(results))
