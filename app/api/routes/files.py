from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile, status

from app.core.limiter import limiter
from app.core.security import CurrentUser, get_current_user
from app.core.validators import UUID_PATTERN
from app.schemas.auth import MessageResponse
from app.schemas.files import (
    FileListResponse,
    FileResponse,
    FileUploadResult,
    MultiFileUploadResponse,
)
from app.services.activity_service import ActivityService
from app.services.file_service import FileService

router = APIRouter()


@router.post("/upload", response_model=MultiFileUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    results: list[FileUploadResult] = []
    uploaded = 0
    failed = 0

    for upload in files:
        try:
            file_record = await FileService.upload_file(current_user.id, upload)
            results.append(
                FileUploadResult(file=file_record, file_name=upload.filename or "unknown", success=True)
            )
            uploaded += 1
        except Exception as e:
            detail = getattr(e, "detail", str(e))
            results.append(
                FileUploadResult(
                    file=None,
                    file_name=upload.filename or "unknown",
                    success=False,
                    error=str(detail),
                )
            )
            failed += 1

    return MultiFileUploadResponse(
        results=results, uploaded_count=uploaded, failed_count=failed
    )


@router.get("", response_model=FileListResponse)
@limiter.limit("60/minute")
async def list_files(
    request: Request,
    search: str | None = Query(default=None),
    file_type: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    # Phase 8: this previously had no limit at all, unlike every other
    # list endpoint in the API (conversion/AI history both cap at 200).
    # Default is generous enough that it shouldn't change behavior for
    # any realistic existing vault size, while preventing an unbounded
    # response for a vault with thousands of files.
    limit: int = Query(default=200, le=500),
    current_user: CurrentUser = Depends(get_current_user),
):
    files = FileService.list_files(
        user_id=current_user.id,
        search=search,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )
    return FileListResponse(files=files, total=len(files))


@router.get("/{file_id}", response_model=FileResponse)
@limiter.limit("60/minute")
async def get_file(
    request: Request,
    file_id: str = Path(pattern=UUID_PATTERN),
    current_user: CurrentUser = Depends(get_current_user),
):
    return FileService.get_file(current_user.id, file_id)


@router.post("/{file_id}/track-download", response_model=MessageResponse)
@limiter.limit("60/minute")
async def track_download(
    request: Request,
    file_id: str = Path(pattern=UUID_PATTERN),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Downloads themselves happen client-side via a signed URL (the backend
    never sees that request), so the frontend calls this endpoint
    alongside triggering the download to record it in the activity feed.
    Best-effort: failures here never block the actual download.
    """
    file = FileService.get_file(current_user.id, file_id)
    ActivityService.log(
        user_id=current_user.id,
        activity_type="file_download",
        description=f"Downloaded \"{file.file_name}\"",
        metadata={"file_id": file_id, "file_type": file.file_type},
    )
    return MessageResponse(message="Download tracked.")


@router.delete("/{file_id}", response_model=MessageResponse)
@limiter.limit("30/minute")
async def delete_file(
    request: Request,
    file_id: str = Path(pattern=UUID_PATTERN),
    current_user: CurrentUser = Depends(get_current_user),
):
    FileService.delete_file(current_user.id, file_id)
    return MessageResponse(message="File deleted successfully.")
