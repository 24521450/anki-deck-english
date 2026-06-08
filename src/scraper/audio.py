"""Audio source chain for ielts-deck.

Resolves Anki [sound:filename.mp3] field values for a word's UK/US
audio by walking a chain of named AudioSource adapters. The chain
order is the single source of truth — config or default
`CHAIN_ORDER = ('cambridge', 'oxford', 'tts')`.

Why the order:
    - Cambridge: 5,228 files on disk, UK/US for ~all 5,002 words.
      Highest quality and coverage.
    - Oxford: 56 files, best-effort supplement.
    - edge-tts: 70 files, last-resort synthesis.

The previous build_notes.py:44-48, 93-107 implemented the chain as a
hard-coded `for src in ('oxford', 'cambridge', 'tts'):` loop — order
inverted from AGENTS.md:60-61 and .harness/reins/scraper/agent.md:20-23.
The wrong order happened to be silent-correct because Oxford had only
56 files, so most lookups fell through to Cambridge. Any future
Oxford file added with inferior quality would silently win.

The interface: pass any object that responds to .exists(filename: str)
-> bool and .ref(filename: str) -> str (the [sound:filename] field
value). FilesystemSource is the production adapter; tests can
inject InMemorySource to assert chain order without touching disk.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

# Single source of truth for chain order. Per AGENTS.md:60-61 and
# .harness/reins/scraper/agent.md:20-23, the order is:
#   1. Cambridge (highest quality + coverage)
#   2. Oxford (best-effort supplement)
#   3. edge-tts (last-resort synthesis)
CHAIN_ORDER: tuple[str, ...] = ("cambridge", "oxford", "tts")

# Per-source filename template: {accent} = 'uk' or 'us', {word} = the
# lookup word. Cambridge and Oxford have a source prefix; raw edge-tts
# output has no prefix.
AUDIO_TEMPLATE: dict[str, str] = {
    "cambridge": "cambridge_{accent}_{word}.mp3",
    "oxford":    "oxford_{accent}_{word}.mp3",
    "tts":       "{accent}_{word}.mp3",
}


class AudioSource(Protocol):
    """Adapter that satisfies the audio lookup seam.

    Production adapter: `FilesystemSource(audio_dir)`. Test adapter:
    any object with the same two methods.
    """

    def exists(self, filename: str) -> bool: ...
    def ref(self, filename: str) -> str: ...


@dataclass(frozen=True)
class FilesystemSource:
    """Production AudioSource — looks up files in a directory on disk.

    `exists()` and `ref()` are both O(1) stat calls. Use one
    FilesystemSource per source (cambridge, oxford, tts) — pass them
    to `find_audio()` directly, or let `default_sources(audio_dir)`
    build the standard set.
    """
    audio_dir: Path

    def exists(self, filename: str) -> bool:
        return (self.audio_dir / filename).exists()

    def ref(self, filename: str) -> str:
        return f"[sound:{filename}]"


def default_sources(audio_dir: Path) -> dict[str, FilesystemSource]:
    """Build the standard source set (cambridge, oxford, tts) bound to
    one directory. Caller passes the result to find_audio().
    """
    return {name: FilesystemSource(audio_dir) for name in CHAIN_ORDER}


def find_audio(
    word: str,
    sources: dict[str, AudioSource],
    chain: Iterable[str] = CHAIN_ORDER,
) -> tuple[str, str]:
    """Walk the chain, return (AudioUK, AudioUS) as [sound:filename] strings.

    Each accent is looked up independently. The first source in `chain`
    whose file exists wins for that accent. Empty string if no source
    has a file for that accent.
    """
    audio_uk, audio_us = "", ""
    for src_name in chain:
        if src_name not in sources:
            continue
        src = sources[src_name]
        template = AUDIO_TEMPLATE[src_name]
        if not audio_uk:
            fn = template.format(accent="uk", word=word)
            if src.exists(fn):
                audio_uk = src.ref(fn)
        if not audio_us:
            fn = template.format(accent="us", word=word)
            if src.exists(fn):
                audio_us = src.ref(fn)
        if audio_uk and audio_us:
            break
    return audio_uk, audio_us
