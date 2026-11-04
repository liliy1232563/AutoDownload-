import pytest

from core.url_validator import URLValidator


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video.mp4",
        "https://cdn.example.org/anime/episode-1.mkv",
        "http://media.example.com/file.mp4",
    ],
)
def test_valid_http_urls(url):
    validator = URLValidator()
    result = validator.validate(url)
    assert result is True


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "ftp://example.com/video.mp4",
        "not-a-url",
        "",
    ],
)
def test_invalid_urls(url):
    validator = URLValidator()

    with pytest.raises((ValueError, TypeError)):
        validator.validate(url)


def test_localhost_is_rejected():
    validator = URLValidator()

    with pytest.raises((ValueError, TypeError)):
        validator.validate("http://127.0.0.1/video.mp4")


def test_private_ip_is_rejected():
    validator = URLValidator()

    with pytest.raises((ValueError, TypeError)):
        validator.validate("http://192.168.1.10/video.mp4")
