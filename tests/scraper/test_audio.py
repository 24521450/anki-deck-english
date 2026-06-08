"""Tests for src.scraper.audio.

Covers:
- Chain order: cambridge > oxford > tts (per AGENTS.md)
- First-match-wins per accent
- Empty chain (no source has the file) returns ('', '')
- Custom chain order is honored (test seam)
- InMemorySource isolates tests from disk
- FilesystemSource is just a thin wrapper (smoke test)
"""
from __future__ import annotations

from pathlib import Path

from src.scraper.audio import (
    AUDIO_TEMPLATE,
    CHAIN_ORDER,
    FilesystemSource,
    default_sources,
    find_audio,
)


class InMemorySource:
    """Test adapter: looks up filenames in a set, returns [sound:fn] refs."""
    def __init__(self, files: set[str]):
        self.files = set(files)

    def exists(self, filename: str) -> bool:
        return filename in self.files

    def ref(self, filename: str) -> str:
        return f"[sound:{filename}]"


def _src(camb=(), ox=(), tts=()) -> dict[str, InMemorySource]:
    return {
        "cambridge": InMemorySource(set(camb)),
        "oxford":    InMemorySource(set(ox)),
        "tts":       InMemorySource(set(tts)),
    }


# ── chain order ────────────────────────────────────────────────────


def test_chain_order_constant_matches_docs():
    """CHAIN_ORDER = cambridge > oxford > tts. AGENTS.md:60-61 contract."""
    assert CHAIN_ORDER == ("cambridge", "oxford", "tts")


def test_cambridge_wins_when_all_three_have_file():
    src = _src(
        camb=("cambridge_uk_run.mp3", "cambridge_us_run.mp3"),
        ox=("oxford_uk_run.mp3", "oxford_us_run.mp3"),
        tts=("uk_run.mp3", "us_run.mp3"),
    )
    uk, us = find_audio("run", src)
    assert uk == "[sound:cambridge_uk_run.mp3]"
    assert us == "[sound:cambridge_us_run.mp3]"


def test_oxford_used_when_cambridge_missing():
    src = _src(
        camb=(),
        ox=("oxford_uk_run.mp3", "oxford_us_run.mp3"),
        tts=("uk_run.mp3", "us_run.mp3"),
    )
    uk, us = find_audio("run", src)
    assert uk == "[sound:oxford_uk_run.mp3]"
    assert us == "[sound:oxford_us_run.mp3]"


def test_tts_used_when_oxford_and_cambridge_missing():
    src = _src(
        camb=(),
        ox=(),
        tts=("uk_run.mp3", "us_run.mp3"),
    )
    uk, us = find_audio("run", src)
    assert uk == "[sound:uk_run.mp3]"   # tts has no prefix
    assert us == "[sound:us_run.mp3]"


def test_empty_when_no_source_has_file():
    src = _src()
    uk, us = find_audio("missing", src)
    assert uk == ""
    assert us == ""


# ── per-accent independence ───────────────────────────────────────


def test_uk_falls_back_independently_of_us():
    """uk has cambridge, us only has oxford. Each accent walks its own chain."""
    src = _src(
        camb=("cambridge_uk_run.mp3",),
        ox=("oxford_us_run.mp3",),
        tts=(),
    )
    uk, us = find_audio("run", src)
    assert uk == "[sound:cambridge_uk_run.mp3]"
    assert us == "[sound:oxford_us_run.mp3]"


def test_uk_found_us_missing_returns_empty_us():
    src = _src(camb=("cambridge_uk_run.mp3",), ox=(), tts=())
    uk, us = find_audio("run", src)
    assert uk == "[sound:cambridge_uk_run.mp3]"
    assert us == ""


# ── custom chain ──────────────────────────────────────────────────


def test_custom_chain_overrides_default():
    """Caller can pass a different chain order. The default is just
    the recommended one; the function honours whatever it's given."""
    src = _src(
        camb=("cambridge_uk_run.mp3",),
        ox=("oxford_uk_run.mp3",),
        tts=("uk_run.mp3",),
    )
    # Reverse the chain: tts wins, then oxford, then cambridge
    uk, _ = find_audio("run", src, chain=("tts", "oxford", "cambridge"))
    assert uk == "[sound:uk_run.mp3]"  # tts template, no prefix


def test_chain_skips_unknown_source_name():
    """A source name not in the `sources` dict is silently skipped."""
    src = _src(camb=("cambridge_uk_run.mp3",))
    # 'oxford' not in src; chain still completes via cambridge
    uk, _ = find_audio("run", src, chain=("oxford", "cambridge"))
    assert uk == "[sound:cambridge_uk_run.mp3]"


# ── file template correctness ─────────────────────────────────────


def test_tts_template_has_no_source_prefix():
    assert AUDIO_TEMPLATE["tts"] == "{accent}_{word}.mp3"


def test_cambridge_oxford_templates_have_source_prefix():
    assert AUDIO_TEMPLATE["cambridge"] == "cambridge_{accent}_{word}.mp3"
    assert AUDIO_TEMPLATE["oxford"]    == "oxford_{accent}_{word}.mp3"


# ── FilesystemSource smoke test ───────────────────────────────────


def test_filesystem_source_exists_and_ref(tmp_path: Path):
    (tmp_path / "cambridge_uk_run.mp3").write_bytes(b"")
    (tmp_path / "cambridge_us_run.mp3").write_bytes(b"")
    src = {"cambridge": FilesystemSource(tmp_path),
           "oxford":    FilesystemSource(tmp_path),
           "tts":       FilesystemSource(tmp_path)}
    uk, us = find_audio("run", src)
    assert uk == "[sound:cambridge_uk_run.mp3]"
    assert us == "[sound:cambridge_us_run.mp3]"


def test_default_sources_builds_chain():
    """default_sources(audio_dir) returns one FilesystemSource per chain entry."""
    srcs = default_sources(Path("/tmp/audio"))
    assert set(srcs.keys()) == set(CHAIN_ORDER)
    for name, src in srcs.items():
        assert isinstance(src, FilesystemSource)
