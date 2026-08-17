import pytest
from gtasks_mcp_server.server import (
    validate_date_format,
    validate_url_format,
    ValidationError,
)


def test_validate_date_format_valid():
    validate_date_format("2026-08-17")


def test_validate_date_format_invalid():
    with pytest.raises(ValidationError):
        validate_date_format("2026-13-45")

    with pytest.raises(ValidationError):
        validate_date_format("17-08-2026")


def test_validate_url_format_valid():
    validate_url_format("https://example.com")
    validate_url_format("http://example.com/path?query=1")


def test_validate_url_format_invalid():
    with pytest.raises(ValidationError):
        validate_url_format("ftp://example.com")

    with pytest.raises(ValidationError):
        validate_url_format("not a url")
