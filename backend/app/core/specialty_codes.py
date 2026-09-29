import re
import unicodedata
from collections.abc import Iterable


MAX_SPECIALTY_CODE_LENGTH = 80

_KNOWN_SPECIALTY_CODES = {
    "cardiologia": "cardiology",
    "pediatria": "pediatrics",
    "cardiologia pediatrica": "pediatric-cardiology",
    "medicina interna": "internal-medicine",
    "medicina general": "general-medicine",
    "no especificada registro historico": "historical-unspecified",
}


def _ascii_words(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value.casefold()))


def canonical_specialty_code(name: str) -> str:
    normalized_name = _ascii_words(name)
    known_code = _KNOWN_SPECIALTY_CODES.get(normalized_name)
    if known_code is not None:
        return known_code
    generated = normalized_name.replace(" ", "-") or "specialty"
    return generated[:MAX_SPECIALTY_CODE_LENGTH].rstrip("-") or "specialty"


def allocate_specialty_code(name: str, existing_codes: Iterable[str]) -> str:
    used = {code.casefold() for code in existing_codes}
    base = canonical_specialty_code(name)
    if base.casefold() not in used:
        return base

    suffix_number = 2
    while True:
        suffix = f"-{suffix_number}"
        prefix = base[: MAX_SPECIALTY_CODE_LENGTH - len(suffix)].rstrip("-") or "specialty"
        candidate = f"{prefix}{suffix}"
        if candidate.casefold() not in used:
            return candidate
        suffix_number += 1


def specialty_code_default(context) -> str:
    return canonical_specialty_code(str(context.get_current_parameters().get("name", "")))
