"""
Shared validation patterns for request input — both path parameters
(via fastapi.Path) and body fields (via pydantic.Field). Centralized
here so the UUID format constraint used across files.py, conversion.py,
and ai.py path parameters stays in exactly one place rather than being
copy-pasted with the risk of drifting out of sync.
"""

# Matches a standard hyphenated UUID, as Supabase always returns for
# every id/*_id column in this schema.
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
