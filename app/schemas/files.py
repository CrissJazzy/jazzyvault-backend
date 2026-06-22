from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class FileType(str, Enum):
    docx = "docx"
    pdf = "pdf"
    txt = "txt"
    jpg = "jpg"
    jpeg = "jpeg"
    png = "png"
    pptx = "pptx"
    xlsx = "xlsx"


class FileResponse(BaseModel):
    id: str
    user_id: str
    file_name: str
    file_url: str
    file_size: int
    file_type: str
    storage_path: str
    created_at: datetime


class FileListResponse(BaseModel):
    files: list[FileResponse]
    total: int


class FileUploadResult(BaseModel):
    file: FileResponse | None = None
    file_name: str
    success: bool
    error: str | None = None


class MultiFileUploadResponse(BaseModel):
    results: list[FileUploadResult]
    uploaded_count: int
    failed_count: int
