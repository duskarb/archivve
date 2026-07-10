import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from capture_playwright import (  # noqa: E402
    _extract_script_navigation_urls,
    _extract_static_image_urls,
    _in_scope,
    _normalize_page_url,
    _origin,
)


def test_normalize_page_url_resolves_relative_and_strips_fragments():
    assert _normalize_page_url(
        "../result.html#score", "https://example.com/work/intro/index.html"
    ) == "https://example.com/work/result.html"


def test_normalize_page_url_rejects_non_navigation_values():
    base = "https://example.com/work/"
    assert _normalize_page_url("#details", base) == ""
    assert _normalize_page_url("javascript:void(0)", base) == ""
    assert _normalize_page_url("mailto:hello@example.com", base) == ""
    assert _normalize_page_url("/users/${id}", base) == ""


def test_extracts_button_and_spa_navigation_destinations():
    source = """
      <button onclick="window.location.href='./next.html'">Next</button>
      <script>
        window.open('https://app.example.net/start#top', '_blank');
        history.pushState({}, '', '/work/history');
        router.push(`/work/final`);
        navigate('/work/history');
      </script>
    """

    assert _extract_script_navigation_urls(source, "https://example.com/work/") == [
        "https://example.com/work/next.html",
        "https://app.example.net/start",
        "https://example.com/work/history",
        "https://example.com/work/final",
    ]


def test_extracts_navigation_from_external_javascript_relative_to_script():
    source = "document.querySelector('button').onclick = () => location.assign('../done.html')"
    assert _extract_script_navigation_urls(
        source, "https://example.com/work/assets/app.js"
    ) == ["https://example.com/work/done.html"]


def test_extracts_images_assigned_after_button_click():
    source = """
      const steps = [
        { image: "images/stone1.jpg" },
        { image: 'images/stone2.webp?v=2' },
      ];
      .hero { background-image: url('../images/final.png'); }
      const placeholder = `data:image/svg+xml,ignored`;
    """

    assert _extract_static_image_urls(
        source, "https://example.com/work/index.html"
    ) == [
        "https://example.com/work/images/stone1.jpg",
        "https://example.com/work/images/stone2.webp?v=2",
        "https://example.com/images/final.png",
    ]


def test_scope_uses_exact_origin_instead_of_string_prefix():
    origins = {_origin("https://example.com/work/")}
    assert _in_scope("https://example.com/another-page", origins)
    assert not _in_scope("https://example.com.evil.test/work/", origins)
    assert not _in_scope("http://example.com/work/", origins)
