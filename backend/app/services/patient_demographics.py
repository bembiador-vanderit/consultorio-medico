"""Canonical document identity; no country-specific format assumptions."""
import unicodedata


def normalize_document(value: str | None) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFKC", value).upper()
    return "".join(char for char in value if not char.isspace() and char not in "-‐‑–—") or None
