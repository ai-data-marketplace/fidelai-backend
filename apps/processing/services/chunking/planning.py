from __future__ import annotations

import math
import re
from typing import Any

from .types import BlockRef, ChunkSpan


class ChunkPlanningEngine:
    def flatten_structure(self, structure: Any) -> list[BlockRef]:
        flattened: list[BlockRef] = []
        if not isinstance(structure, list):
            return flattened

        for page_idx, page in enumerate(structure):
            if not isinstance(page, dict):
                continue
            page_number = int(page.get("page") or (page_idx + 1))
            blocks = page.get("blocks") or []
            if not isinstance(blocks, list):
                continue

            for block_index, block in enumerate(blocks):
                if not isinstance(block, dict):
                    continue
                block_text = str(block.get("text", "") or "").strip()
                if not block_text:
                    continue
                block_type = str(block.get("type") or "paragraph")
                confidence = float(block.get("confidence") or 0.0)
                bbox = block.get("bbox")
                flattened.append(
                    BlockRef(
                        page_number=page_number,
                        block_index=block_index,
                        block_type=block_type,
                        text=block_text,
                        confidence=confidence,
                        bbox=bbox,
                    )
                )

        return flattened

    def plan_chunk_spans(
        self,
        *,
        full_text: str,
        blocks: list[BlockRef],
        target_tokens: int,
        max_tokens: int,
    ) -> list[ChunkSpan]:
        if blocks:
            spans = self._plan_from_blocks(
                full_text=full_text,
                blocks=blocks,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
            )
            if spans:
                avg_quality = sum(s.mapping_quality for s in spans) / len(spans)
                if avg_quality >= 0.70:
                    return spans

        return self._plan_from_full_text(
            full_text=full_text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
        )

    def _plan_from_blocks(
        self,
        *,
        full_text: str,
        blocks: list[BlockRef],
        target_tokens: int,
        max_tokens: int,
    ) -> list[ChunkSpan]:
        segments = self._segment_blocks(blocks)
        mapped_segments, mapping_ratio = self._map_segments_to_full_text(full_text, segments)

        if mapping_ratio < 0.60:
            return []

        spans: list[ChunkSpan] = []
        current_blocks: list[BlockRef] = []
        current_start: int | None = None
        current_end: int | None = None
        current_tokens = 0
        mapped_block_count = 0
        total_block_count = 0

        for segment in mapped_segments:
            seg_blocks = segment["blocks"]
            seg_start = segment.get("char_start")
            seg_end = segment.get("char_end")
            seg_tokens = int(segment.get("token_estimate") or 0)
            seg_mapped = bool(seg_start is not None and seg_end is not None and seg_end > seg_start)

            total_block_count += len(seg_blocks)
            mapped_block_count += len(seg_blocks) if seg_mapped else 0

            if not seg_mapped:
                continue

            if current_blocks and (current_tokens + seg_tokens) > max_tokens:
                span = self._finalize_span(
                    full_text=full_text,
                    blocks=current_blocks,
                    char_start=current_start,
                    char_end=current_end,
                    mapping_method="block_regex",
                    mapping_quality=(mapped_block_count / max(1, total_block_count)),
                )
                if span:
                    spans.append(span)

                current_blocks = []
                current_start = None
                current_end = None
                current_tokens = 0

            if seg_tokens > max_tokens and seg_start is not None and seg_end is not None:
                spans.extend(
                    self._split_span_by_full_text(
                        full_text=full_text,
                        char_start=seg_start,
                        char_end=seg_end,
                        source_blocks=seg_blocks,
                        target_tokens=target_tokens,
                        max_tokens=max_tokens,
                        mapping_quality=(mapped_block_count / max(1, total_block_count)),
                    )
                )
                continue

            if current_start is None or seg_start < current_start:
                current_start = seg_start
            if current_end is None or seg_end > current_end:
                current_end = seg_end
            current_blocks.extend(seg_blocks)
            current_tokens += seg_tokens

            if current_tokens >= target_tokens:
                span = self._finalize_span(
                    full_text=full_text,
                    blocks=current_blocks,
                    char_start=current_start,
                    char_end=current_end,
                    mapping_method="block_regex",
                    mapping_quality=(mapped_block_count / max(1, total_block_count)),
                )
                if span:
                    spans.append(span)

                current_blocks = []
                current_start = None
                current_end = None
                current_tokens = 0

        if current_blocks:
            span = self._finalize_span(
                full_text=full_text,
                blocks=current_blocks,
                char_start=current_start,
                char_end=current_end,
                mapping_method="block_regex",
                mapping_quality=(mapped_block_count / max(1, total_block_count)),
            )
            if span:
                spans.append(span)

        return self._dedupe_and_sort_spans(spans)

    def _segment_blocks(self, blocks: list[BlockRef]) -> list[list[BlockRef]]:
        segments: list[list[BlockRef]] = []
        current: list[BlockRef] = []

        def flush() -> None:
            nonlocal current
            if current:
                segments.append(current)
                current = []

        idx = 0
        while idx < len(blocks):
            block = blocks[idx]
            btype = (block.block_type or "paragraph").lower()

            if btype == "heading":
                flush()
                current.append(block)
                idx += 1
                continue

            if btype == "table":
                flush()
                segments.append([block])
                idx += 1
                continue

            if btype == "list_item":
                flush()
                group = [block]
                idx += 1
                while idx < len(blocks) and (blocks[idx].block_type or "").lower() == "list_item":
                    group.append(blocks[idx])
                    idx += 1
                segments.append(group)
                continue

            current.append(block)
            idx += 1

        flush()
        return segments

    def _map_segments_to_full_text(
        self,
        full_text: str,
        segments: list[list[BlockRef]],
    ) -> tuple[list[dict[str, Any]], float]:
        cursor = 0
        mapped_segments: list[dict[str, Any]] = []

        total_blocks = sum(len(seg) for seg in segments) or 1
        mapped_blocks = 0

        for seg in segments:
            seg_start: int | None = None
            seg_end: int | None = None
            seg_tokens = 0

            for block in seg:
                match = self._find_block_span(full_text, block.text, start_at=cursor)
                if match is None:
                    match = self._find_block_span(full_text, block.text, start_at=0)

                if match is None:
                    continue

                start, end = match
                mapped_blocks += 1
                cursor = max(cursor, end)

                if seg_start is None or start < seg_start:
                    seg_start = start
                if seg_end is None or end > seg_end:
                    seg_end = end

                seg_tokens += estimate_tokens(full_text[start:end])

            mapped_segments.append(
                {
                    "blocks": seg,
                    "char_start": seg_start,
                    "char_end": seg_end,
                    "token_estimate": seg_tokens,
                }
            )

        return mapped_segments, (mapped_blocks / total_blocks)

    def _find_block_span(self, full_text: str, block_text: str, *, start_at: int) -> tuple[int, int] | None:
        pattern = self._block_text_to_whitespace_flexible_regex(block_text)
        if not pattern:
            return None

        match = re.search(pattern, full_text[start_at:], flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        start = start_at + match.start()
        end = start_at + match.end()
        if end <= start:
            return None
        return start, end

    def _block_text_to_whitespace_flexible_regex(self, text: str) -> str | None:
        cleaned = self._normalize_for_matching(text)
        if not cleaned:
            return None

        parts = [re.escape(part) for part in cleaned.split(" ") if part]
        if not parts:
            return None
        return r"(?:" + r"\s+".join(parts) + r")"

    def _normalize_for_matching(self, text: str) -> str:
        t = (text or "").strip()
        t = t.replace("\u200b", "").replace("\ufeff", "")
        t = re.sub(r"\s+", " ", t)
        return t.strip()

    def _plan_from_full_text(self, *, full_text: str, target_tokens: int, max_tokens: int) -> list[ChunkSpan]:
        spans: list[ChunkSpan] = []
        sentence_spans = self._split_full_text_into_sentence_spans(full_text)

        current_start: int | None = None
        current_end: int | None = None
        current_tokens = 0
        current_blocks: list[BlockRef] = []

        for start, end in sentence_spans:
            sentence = full_text[start:end]
            sent_tokens = estimate_tokens(sentence)

            if sent_tokens > max_tokens:
                if current_start is not None and current_end is not None and current_end > current_start:
                    spans.append(
                        ChunkSpan(
                            char_start=current_start,
                            char_end=current_end,
                            source_blocks=current_blocks,
                            mapping_method="fulltext_sentence",
                            mapping_quality=1.0,
                        )
                    )
                    current_start = None
                    current_end = None
                    current_tokens = 0
                    current_blocks = []

                spans.extend(
                    self._split_span_by_full_text(
                        full_text=full_text,
                        char_start=start,
                        char_end=end,
                        source_blocks=[],
                        target_tokens=target_tokens,
                        max_tokens=max_tokens,
                        mapping_quality=1.0,
                        mapping_method="fulltext_window",
                    )
                )
                continue

            if current_start is not None and (current_tokens + sent_tokens) > max_tokens:
                spans.append(
                    ChunkSpan(
                        char_start=current_start,
                        char_end=current_end or current_start,
                        source_blocks=current_blocks,
                        mapping_method="fulltext_sentence",
                        mapping_quality=1.0,
                    )
                )
                current_start = None
                current_end = None
                current_tokens = 0
                current_blocks = []

            if current_start is None:
                current_start = start
                current_end = end
                current_tokens = sent_tokens
            else:
                current_end = end
                current_tokens += sent_tokens

            if current_tokens >= target_tokens:
                spans.append(
                    ChunkSpan(
                        char_start=current_start,
                        char_end=current_end or current_start,
                        source_blocks=current_blocks,
                        mapping_method="fulltext_sentence",
                        mapping_quality=1.0,
                    )
                )
                current_start = None
                current_end = None
                current_tokens = 0
                current_blocks = []

        if current_start is not None and current_end is not None and current_end > current_start:
            spans.append(
                ChunkSpan(
                    char_start=current_start,
                    char_end=current_end,
                    source_blocks=current_blocks,
                    mapping_method="fulltext_sentence",
                    mapping_quality=1.0,
                )
            )

        return self._dedupe_and_sort_spans(spans)

    def _split_full_text_into_sentence_spans(self, full_text: str) -> list[tuple[int, int]]:
        text = full_text
        if not text:
            return []

        boundaries = []
        for match in re.finditer(r"\n\n+", text):
            boundaries.append(match.end())

        for match in re.finditer(r"[.!?\u1362\u1367\u1368](?:\s+|$)", text):
            boundaries.append(match.end())

        boundaries = sorted(set(b for b in boundaries if 0 < b < len(text)))

        spans = []
        start = 0
        for boundary in boundaries:
            end = boundary
            if end > start:
                spans.append((start, end))
                start = end
        if start < len(text):
            spans.append((start, len(text)))

        trimmed: list[tuple[int, int]] = []
        for start, end in spans:
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            if end > start:
                trimmed.append((start, end))

        return trimmed

    def _split_span_by_full_text(
        self,
        *,
        full_text: str,
        char_start: int,
        char_end: int,
        source_blocks: list[BlockRef],
        target_tokens: int,
        max_tokens: int,
        mapping_quality: float,
        mapping_method: str = "block_window",
    ) -> list[ChunkSpan]:
        text = full_text[char_start:char_end]
        if not text.strip():
            return []

        spans: list[ChunkSpan] = []
        words = list(re.finditer(r"\S+", text))
        if not words:
            return []

        words_per_token = 1.0
        max_words = int(max_tokens * words_per_token)
        target_words = int(target_tokens * words_per_token)
        max_words = max(20, max_words)
        target_words = max(10, target_words)

        i = 0
        while i < len(words):
            j = min(len(words), i + max_words)

            preferred = min(len(words), i + target_words)
            if preferred < j:
                j = preferred

            start = char_start + words[i].start()
            end = char_start + words[j - 1].end()

            while end < char_end and full_text[end].isspace():
                end += 1

            spans.append(
                ChunkSpan(
                    char_start=start,
                    char_end=end,
                    source_blocks=source_blocks,
                    mapping_method=mapping_method,
                    mapping_quality=mapping_quality,
                )
            )
            i = j

        return spans

    def _finalize_span(
        self,
        *,
        full_text: str,
        blocks: list[BlockRef],
        char_start: int | None,
        char_end: int | None,
        mapping_method: str,
        mapping_quality: float,
    ) -> ChunkSpan | None:
        if char_start is None or char_end is None:
            return None
        char_start = max(0, int(char_start))
        char_end = min(len(full_text), int(char_end))
        if char_end <= char_start:
            return None
        return ChunkSpan(
            char_start=char_start,
            char_end=char_end,
            source_blocks=blocks,
            mapping_method=mapping_method,
            mapping_quality=float(mapping_quality),
        )

    def _dedupe_and_sort_spans(self, spans: list[ChunkSpan]) -> list[ChunkSpan]:
        seen = set()
        deduped: list[ChunkSpan] = []
        for span in spans:
            key = (span.char_start, span.char_end)
            if key in seen:
                continue
            if span.char_end <= span.char_start:
                continue
            seen.add(key)
            deduped.append(span)

        deduped.sort(key=lambda span: (span.char_start, span.char_end))
        return deduped


def estimate_tokens(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0

    words = len(re.findall(r"\S+", normalized))
    if words:
        return int(math.ceil(words * 1.10))
    return max(1, int(math.ceil(len(normalized) / 4)))
