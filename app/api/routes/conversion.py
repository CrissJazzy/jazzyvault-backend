from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.core.limiter import limiter
from app.core.security import CurrentUser, get_current_user
from app.core.validators import UUID_PATTERN
from app.db.supabase_client import get_supabase_admin
from app.schemas.conversion import (
    ConversionHistoryEntry,
    ConversionHistoryResponse,
    ConversionListResponse,
    ConversionResponse,
    ConvertRequest,
)
from app.services.conversion_service import ConversionService

router = APIRouter()


@router.post("", response_model=ConversionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def convert_file(
    request: Request,
    payload: ConvertRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await ConversionService.convert_file(
        user_id=current_user.id,
        file_id=payload.file_id,
        target_format=payload.target_format,
    )


@router.get("/history", response_model=ConversionHistoryResponse)
@limiter.limit("30/minute")
async def get_conversion_history(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(
        default=None, description="Search by the source file's name"
    ),
    conversion_type: str | None = Query(
        default=None,
        alias="type",
        description="Filter by 'input_format-output_format', e.g. 'docx-pdf'",
    ),
    date_from: str | None = Query(
        default=None, description="ISO date/datetime lower bound on created_at"
    ),
    date_to: str | None = Query(
        default=None, description="ISO date/datetime upper bound on created_at"
    ),
    sort_order: str = Query(
        default="desc", description="'desc' for newest first, 'asc' for oldest first"
    ),
    limit: int = Query(default=50, le=200),
    current_user: CurrentUser = Depends(get_current_user),
):
    admin = get_supabase_admin()

    # Embed the related file row so we can search/display the source
    # file's name and size without a second round trip. supabase-py
    # supports this via PostgREST's embedded resource syntax. The
    # explicit "!conversions_input_file_fkey" disambiguation is
    # REQUIRED here, not optional — conversions has two foreign keys
    # to files (input_file_id and output_file_id), and PostgREST can't
    # tell which one to embed without it. The constraint name is set
    # explicitly in supabase/migrations/005_rename_conversion_fkeys.sql.
    select_clause = "*, input_file:files!conversions_input_file_fkey(file_name, file_size)"

    query = (
        admin.table("conversions")
        .select(select_clause)
        .eq("user_id", current_user.id)
    )

    if status_filter:
        query = query.eq("status", status_filter)

    if conversion_type and "-" in conversion_type:
        in_fmt, out_fmt = conversion_type.split("-", 1)
        query = query.eq("input_format", in_fmt).eq("output_format", out_fmt)

    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)

    ascending = sort_order.lower() == "asc"
    query = query.order("created_at", desc=not ascending).limit(limit)

    result = query.execute()
    rows = result.data

    # Client-side filename search: PostgREST can't easily filter on a
    # joined table's column with ilike in a single query via supabase-py,
    # so we filter the (already user + limit scoped) result set here.
    # Fine at this scale; revisit with a Postgres view/RPC if conversion
    # history grows very large per user.
    if search:
        needle = search.lower()
        rows = [
            r for r in rows
            if r.get("input_file") and needle in (r["input_file"].get("file_name") or "").lower()
        ]

    entries = [_to_history_entry(row) for row in rows]
    return ConversionHistoryResponse(conversions=entries, total=len(entries))


def _to_history_entry(row: dict) -> ConversionHistoryEntry:
    input_file = row.get("input_file") or {}
    flat = dict(row)
    flat.pop("input_file", None)
    flat["file_name"] = input_file.get("file_name", "Unknown file")
    flat["file_size"] = input_file.get("file_size", 0)
    return ConversionHistoryEntry(**flat)


@router.get("/{conversion_id}", response_model=ConversionResponse)
@limiter.limit("60/minute")
async def get_conversion(
    request: Request,
    conversion_id: str = Path(pattern=UUID_PATTERN),
    current_user: CurrentUser = Depends(get_current_user),
):
    admin = get_supabase_admin()
    result = (
        admin.table("conversions")
        .select("*")
        .eq("id", conversion_id)
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Conversion not found.")
    return ConversionResponse(**result.data)
