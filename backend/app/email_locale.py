"""Resolve the language selected in the web UI for transactional email."""

from fastapi import Request

SUPPORTED_EMAIL_LOCALES = frozenset({"en", "de", "fr", "es", "it"})


def resolve_email_locale(value: str | None) -> str:
    """Normalize an Accept-Language value to a supported base language."""
    if not value:
        return "en"
    for preference in value.split(","):
        language = preference.split(";", 1)[0].strip().replace("_", "-").split("-", 1)[0]
        language = language.lower()
        if language in SUPPORTED_EMAIL_LOCALES:
            return language
    return "en"


def request_email_locale(request: Request) -> str:
    return resolve_email_locale(request.headers.get("accept-language"))
