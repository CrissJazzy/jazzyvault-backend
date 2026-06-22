import uuid

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.schemas.files import FileResponse
from app.services.activity_service import ActivityService
from app.utils.file_validation import get_extension, is_allowed_file, sanitize_filename

MAX_UPLOAD_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
SIGNED_URL_EXPIRY_SECONDS = 60 * 60  # 1 hour


def _sign_url(storage_path: str) -> str:
    """
    The 'jazzyvault-files' bucket is private (RLS-gated), so files are
    never served via get_public_url() — that only works for public
    buckets and silently produces a URL that 403s on a private one.
    Instead we mint a short-lived signed URL on every read, rather than
    storing one in the DB, since a stored signed URL would eventually
    expire and break.
    """
    admin = get_supabase_admin()
    try:
        result = admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
            storage_path, SIGNED_URL_EXPIRY_SECONDS
        )
        return result.get("signedURL") or result.get("signedUrl") or ""
    except Exception:
        return ""


def _sign_urls_batch(storage_paths: list[str]) -> dict[str, str]:
    """
    Phase 8 performance fix: signs multiple Storage paths in a single
    Supabase API call instead of one call per file. Before this, listing
    a vault with N files made N sequential signed-URL requests just to
    render the list — e.g. 50 files meant 50 round trips. Returns a
    {storage_path: signed_url} map; any path that fails to sign maps to
    "" rather than raising, matching _sign_url()'s existing fail-soft
    behavior so one bad row never breaks the whole list.

    Defensive about response shape: the exact per-item key names
    (signedURL/signedUrl/path) aren't independently verifiable offline
    in this environment, so this tries the documented/likely shapes and
    falls back to "" per item on anything unexpected, rather than
    raising and breaking the entire file list over one signing quirk.
    """
    if not storage_paths:
        return {}

    admin = get_supabase_admin()
    url_by_path: dict[str, str] = {p: "" for p in storage_paths}

    try:
        results = admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_urls(
            storage_paths, SIGNED_URL_EXPIRY_SECONDS
        )
    except Exception:
        # Fall back to per-file signing rather than returning all-empty —
        # slower, but still correct, if the batch call itself fails for
        # a reason that wouldn't affect individual calls (e.g. a
        # malformed batch request).
        return {p: _sign_url(p) for p in storage_paths}

    for i, item in enumerate(results or []):
        # Prefer matching by the path the API echoes back, if present;
        # fall back to positional matching against the input list,
        # since create_signed_urls is documented to preserve input order.
        path_key = item.get("path") or item.get("Key") or (
            storage_paths[i] if i < len(storage_paths) else None
        )
        signed = item.get("signedURL") or item.get("signedUrl") or ""
        if path_key in url_by_path:
            url_by_path[path_key] = signed

    return url_by_path


def _to_file_response(row: dict) -> FileResponse:
    row = dict(row)
    row["file_url"] = _sign_url(row["storage_path"])
    return FileResponse(**row)


class FileService:
    @staticmethod
    async def upload_file(user_id: str, upload: UploadFile) -> FileResponse:
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is missing a filename.",
            )

        content_type = upload.content_type or "application/octet-stream"
        if not is_allowed_file(upload.filename, content_type):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{upload.filename}' is not a supported file type.",
            )

        contents = await upload.read()
        file_size = len(contents)

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{upload.filename}' is empty.",
            )

        if file_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"'{upload.filename}' exceeds the "
                    f"{settings.MAX_UPLOAD_SIZE_MB}MB upload limit."
                ),
            )

        ext = get_extension(upload.filename)
        # Sanitize AFTER validating against the original (so error
        # messages above still reference exactly what the user typed),
        # but BEFORE it's used anywhere persisted — the storage path,
        # the DB record, and therefore eventually the download filename
        # a browser sees. See file_validation.sanitize_filename for why.
        safe_filename = sanitize_filename(upload.filename)
        storage_path = f"{user_id}/{uuid.uuid4()}-{safe_filename}"

        admin = get_supabase_admin()

        try:
            admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                storage_path,
                contents,
                file_options={"content-type": content_type},
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to upload '{upload.filename}' to storage: {e}",
            )

        try:
            result = (
                admin.table("files")
                .insert(
                    {
                        "user_id": user_id,
                        "file_name": safe_filename,
                        "storage_path": storage_path,
                        # file_url is a required NOT NULL column for
                        # readability/back-compat, but signed URLs expire,
                        # so this stored value is never trusted for actual
                        # downloads — _sign_url() always regenerates fresh
                        # ones at read time. Storing the storage_path here
                        # as a placeholder keeps the schema simple.
                        "file_url": storage_path,
                        "file_size": file_size,
                        "file_type": ext,
                    }
                )
                .execute()
            )
        except Exception as e:
            # Roll back the storage object if the DB insert fails, so we
            # don't leak orphaned files that never appear in the vault.
            try:
                admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove(
                    [storage_path]
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file record for '{upload.filename}': {e}",
            )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file record for '{upload.filename}'.",
            )

        ActivityService.log(
            user_id=user_id,
            activity_type="file_upload",
            description=f"Uploaded \"{safe_filename}\"",
            metadata={"file_id": result.data[0]["id"], "file_type": ext},
        )

        return _to_file_response(result.data[0])

    @staticmethod
    def list_files(
        user_id: str,
        search: str | None = None,
        file_type: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 200,
    ) -> list[FileResponse]:
        admin = get_supabase_admin()
        query = admin.table("files").select("*").eq("user_id", user_id)

        if search:
            query = query.ilike("file_name", f"%{search}%")
        if file_type:
            query = query.eq("file_type", file_type)

        valid_sort_columns = {"created_at", "file_name", "file_size"}
        if sort_by not in valid_sort_columns:
            sort_by = "created_at"
        ascending = sort_order.lower() == "asc"

        query = query.order(sort_by, desc=not ascending).limit(limit)
        result = query.execute()
        rows = result.data

        # Phase 8 perf fix: one batched signing call for the whole page
        # of results instead of one call per row (see _sign_urls_batch).
        storage_paths = [row["storage_path"] for row in rows]
        signed_urls = _sign_urls_batch(storage_paths)

        responses = []
        for row in rows:
            row = dict(row)
            row["file_url"] = signed_urls.get(row["storage_path"], "")
            responses.append(FileResponse(**row))
        return responses

    @staticmethod
    def get_file(user_id: str, file_id: str) -> FileResponse:
        admin = get_supabase_admin()
        result = (
            admin.table("files")
            .select("*")
            .eq("id", file_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
            )
        return _to_file_response(result.data)

    @staticmethod
    def delete_file(user_id: str, file_id: str) -> None:
        admin = get_supabase_admin()
        existing = FileService.get_file(user_id, file_id)

        try:
            admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove(
                [existing.storage_path]
            )
        except Exception:
            # If the storage object is already gone, proceed to clean up
            # the DB record anyway rather than leaving a dangling row.
            pass

        admin.table("files").delete().eq("id", file_id).eq(
            "user_id", user_id
        ).execute()

        ActivityService.log(
            user_id=user_id,
            activity_type="file_delete",
            description=f"Deleted \"{existing.file_name}\"",
            metadata={"file_id": file_id, "file_type": existing.file_type},
        )
