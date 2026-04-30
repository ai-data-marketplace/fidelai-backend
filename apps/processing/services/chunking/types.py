from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_TARGET_TOKENS = 50
DEFAULT_MAX_TOKENS = 100
PIPELINE_VERSION = "chunking_v1"


@dataclass(frozen=True)
class BlockRef:
    page_number: int
    block_index: int
    block_type: str
    text: str
    confidence: float
    bbox: Any | None

    @property
    def ref(self) -> str:
        return f"p{self.page_number}:b{self.block_index}"


@dataclass(frozen=True)
class ChunkSpan:
    char_start: int
    char_end: int
    source_blocks: list[BlockRef]
    mapping_method: str
    mapping_quality: float
    close_reason: str = ""
