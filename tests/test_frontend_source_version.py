from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_archive_source_is_versioned_by_manifest_hash():
    source = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "const version = clean(row.sha256) || clean(row.archived_date);" in source
    assert "source: waczSource(row)" in source
