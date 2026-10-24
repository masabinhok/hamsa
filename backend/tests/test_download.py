import pytest

from app.ingest.download import is_platform_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.facebook.com/reel/1",
        "https://m.facebook.com/story.php?id=1",
        "https://fb.watch/abc/",
        "https://vm.tiktok.com/ZM1/",
        "https://youtu.be/abc",
        "https://x.com/a/status/1",
        "http://twitter.com/a/status/1",
        "https://www.instagram.com/reel/A/",
    ],
)
def test_post_links_on_the_platforms_are_fetched(url: str) -> None:
    assert is_platform_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/a/b",
        "http://localhost:6333/collections",
        "http://127.0.0.1:8000/desk/queue",
        "https://facebook.com.evil.example/reel/1",
        "https://evilfacebook.com/reel/1",
        "file:///etc/passwd",
        "ftp://youtube.com/x",
    ],
)
def test_other_and_internal_addresses_are_not(url: str) -> None:
    assert not is_platform_url(url)
