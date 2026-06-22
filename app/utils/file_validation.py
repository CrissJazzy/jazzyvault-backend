import re
import unicodedata

ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    "pdf": {"application/pdf"},
    "txt": {"text/plain"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "png": {"image/png"},
    # Future-ready, per project spec — accepted but conversion support
    # for these lands in a later phase.
    "pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    },
}

ALL_ALLOWED_MIME_TYPES: set[str] = {
    mime for mimes in ALLOWED_EXTENSIONS.values() for mime in mimes
}


def get_extension(filename: str) -> str | None:
    if "." not in filename:
        return None
    return filename.rsplit(".", 1)[1].lower()


def is_allowed_file(filename: str, content_type: str) -> bool:
    ext = get_extension(filename)
    if ext is None or ext not in ALLOWED_EXTENSIONS:
        return False
    # Browsers/OSes are inconsistent about content_type for some formats
    # (e.g. txt can arrive as text/plain;charset=utf-8). Normalize before
    # comparing, and fall back to trusting the extension if content_type
    # is empty/generic, since the real gate is server-side re-validation
    # during conversion (Phase 4).
    normalized = content_type.split(";")[0].strip().lower()
    if not normalized or normalized == "application/octet-stream":
        return True
    return normalized in ALLOWED_EXTENSIONS[ext]


# --- Phase 8: Filename sanitization ---------------------------------
# Client-supplied filenames (upload.filename) are attacker-controlled
# and, before this phase, were embedded directly into Supabase Storage
# paths (f"{user_id}/{uuid}-{filename}") and into the DB's file_name
# column with no sanitization at all. This doesn't enable cross-user
# access (Storage RLS policies already scope every path to
# auth.uid()/... — see migration 002), but an unsanitized filename can
# still: break Storage's own path validation (causing confusing upload
# failures instead of a clean 400), inject path separators or null
# bytes, or contain characters that misbehave in Content-Disposition
# headers on download. Sanitizing server-side, once, here, is simpler
# and more robust than trying to enumerate every dangerous character.

_UNSAFE_FILENAME_CHARS = re.compile(r'[\/\\:*?"<>|\x00-\x1f]')
MAX_FILENAME_LENGTH = 200


def sanitize_filename(filename: str) -> str:
    """
    Returns a filename safe to embed in a Storage path and to send back
    in a Content-Disposition header. Preserves the original extension
    and as much of the readable name as possible — this is a sanitizer,
    not a slugifier, so spaces and most punctuation are kept.
    """
    # Normalize unicode (e.g. combining characters) and strip anything
    # that didn't survive ASCII normalization gracefully, rather than
    # rejecting non-Latin filenames outright.
    normalized = unicodedata.normalize("NFKC", filename)

    # Take just the basename in case a path was smuggled in (handles
    # both / and \ separators regardless of host OS).
    normalized = normalized.replace("\\", "/").split("/")[-1]

    # Strip control characters and filesystem-unsafe characters.
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", normalized).strip()

    # Strip leading dots (hidden files / ".." traversal remnants) but
    # keep the rest of the extension structure intact.
    cleaned = cleaned.lstrip(".")

    if not cleaned:
        cleaned = "file"

    # Truncate, but preserve the extension when doing so.
    if len(cleaned) > MAX_FILENAME_LENGTH:
        ext = get_extension(cleaned)
        if ext:
            stem = cleaned[: -(len(ext) + 1)]
            stem = stem[: MAX_FILENAME_LENGTH - len(ext) - 1]
            cleaned = f"{stem}.{ext}"
        else:
            cleaned = cleaned[:MAX_FILENAME_LENGTH]

    return cleaned
