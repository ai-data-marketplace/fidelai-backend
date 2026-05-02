from __future__ import annotations

import math
import re
from typing import Any
from .types import DEFAULT_TARGET_TOKENS

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
        spans = self._plan_from_full_text(
            full_text=full_text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
        )

        if spans:
            return spans

        if blocks:
            return self._plan_from_blocks(
                full_text=full_text,
                blocks=blocks,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
            )

        return []

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
                    close_reason="max_tokens_reached_at_block_boundary",
                )
                if span:
                    spans.append(span)

                current_blocks = []
                current_start = None
                current_end = None
                current_tokens = 0

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
                    close_reason="target_tokens_reached_at_block_boundary",
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
                close_reason="end_of_document",
            )
            if span:
                spans.append(span)

        return self._dedupe_and_sort_spans(spans, full_text)

    def _segment_blocks(self, blocks: list[BlockRef]) -> list[list[BlockRef]]:
        segments: list[list[BlockRef]] = []
        current: list[BlockRef] = []
        document_title = self._detect_document_title(blocks)
        current_page_number: int | None = None
        page_block_index = 0

        def flush() -> None:
            nonlocal current
            if current:
                segments.append(current)
                current = []

        idx = 0
        while idx < len(blocks):
            block = blocks[idx]
            if current_page_number != block.page_number:
                flush()
                current_page_number = block.page_number
                page_block_index = 0

            if self._should_skip_block(block, document_title=document_title, page_block_index=page_block_index):
                page_block_index += 1
                idx += 1
                continue

            btype = (block.block_type or "paragraph").lower()

            if btype == "heading":
                flush()
                current.append(block)
                page_block_index += 1
                idx += 1
                continue

            if btype == "table":
                flush()
                segments.append([block])
                page_block_index += 1
                idx += 1
                continue

            if btype == "list_item":
                flush()
                group = [block]
                page_block_index += 1
                idx += 1
                while idx < len(blocks):
                    next_block = blocks[idx]
                    if next_block.page_number != block.page_number:
                        break
                    if (next_block.block_type or "").lower() != "list_item":
                        break
                    if self._should_skip_block(
                        next_block,
                        document_title=document_title,
                        page_block_index=page_block_index,
                    ):
                        page_block_index += 1
                        idx += 1
                        continue
                    group.append(next_block)
                    page_block_index += 1
                    idx += 1
                segments.append(group)
                continue

            if self._is_title_like_block(block, is_page_start=(page_block_index <= 1)):
                flush()
                segments.append([block])
                page_block_index += 1
                idx += 1
                continue

            current.append(block)
            page_block_index += 1
            idx += 1

        flush()
        return segments

    def _detect_document_title(self, blocks: list[BlockRef]) -> str | None:
        if not blocks:
            return None
        first_page = blocks[0].page_number
        for block in blocks:
            if block.page_number != first_page:
                break
            if (block.text or "").strip():
                return self._normalize_for_matching(block.text)
        return None

    def _should_skip_block(self, block: BlockRef, *, document_title: str | None, page_block_index: int) -> bool:
        text = self._normalize_for_matching(block.text)
        if not text:
            return True

        if self._looks_like_page_number(block):
            return True

        if document_title and block.page_number > 1 and page_block_index <= 1 and text == document_title:
            return True

        return False

    def _looks_like_page_number(self, block: BlockRef) -> bool:
        text = (block.text or "").strip()
        if not text.isdigit():
            return False

        bbox = block.bbox or []
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            top = float(bbox[1])
            bottom = float(bbox[3])
            return top >= 700 or bottom >= 720
        return len(text) <= 3

    def _is_title_like_block(self, block: BlockRef, *, is_page_start: bool = False) -> bool:
        text = self._normalize_for_matching(block.text)
        if not text:
            return False

        words = text.split(" ")
        word_count = len(words)
        char_count = len(text)
        if word_count > 10 or char_count > 80:
            return False

        bbox = block.bbox or []
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            top = float(bbox[1])
            height = float(bbox[3]) - float(bbox[1])
            if top <= 120 and height <= 45:
                return True

        if is_page_start and word_count <= 6:
            return True

        return False

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

        index = 0
        while index < len(sentence_spans):
            start, end = sentence_spans[index]
            sentence = full_text[start:end]
            sent_tokens = estimate_tokens(sentence)

            if current_start is None:
                if sent_tokens <= max_tokens:
                    current_start = start
                    current_end = end
                    current_tokens = sent_tokens
                    if current_tokens >= target_tokens:
                        spans.append(
                            ChunkSpan(
                                char_start=current_start,
                                char_end=current_end or current_start,
                                source_blocks=current_blocks,
                                mapping_method="fulltext_sentence",
                                mapping_quality=1.0,
                                close_reason="target_tokens_reached_at_sentence_boundary",
                            )
                        )
                        current_start = None
                        current_end = None
                        current_tokens = 0
                        current_blocks = []
                    index += 1
                    continue

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
                        close_reason="sentence_over_max_allowed",
                    )
                )
                index += 1
                continue

            proposed_tokens = current_tokens + sent_tokens

            if proposed_tokens <= max_tokens:
                current_end = end
                current_tokens = proposed_tokens
                if current_tokens >= target_tokens:
                    spans.append(
                        ChunkSpan(
                            char_start=current_start,
                            char_end=current_end or current_start,
                            source_blocks=current_blocks,
                            mapping_method="fulltext_sentence",
                            mapping_quality=1.0,
                            close_reason="target_tokens_reached_at_sentence_boundary",
                        )
                    )
                    current_start = None
                    current_end = None
                    current_tokens = 0
                    current_blocks = []
                index += 1
                continue

            spans.append(
                ChunkSpan(
                    char_start=current_start,
                    char_end=self._trim_end_to_safe_boundary(full_text, current_start, current_end or current_start),
                    source_blocks=current_blocks,
                    mapping_method="fulltext_sentence",
                    mapping_quality=1.0,
                    close_reason="max_tokens_reached_between_sentences",
                )
            )
            current_start = None
            current_end = None
            current_tokens = 0
            current_blocks = []

        if current_start is not None and current_end is not None and current_end > current_start:
            adj_end = self._trim_end_to_safe_boundary(full_text, current_start, current_end)
            spans.append(
                ChunkSpan(
                    char_start=current_start,
                    char_end=adj_end,
                    source_blocks=current_blocks,
                    mapping_method="fulltext_sentence",
                    mapping_quality=1.0,
                    close_reason="end_of_document",
                )
            )

        return self._dedupe_and_sort_spans(spans, full_text)

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
        close_reason: str = "sentence_over_max_allowed",
    ) -> list[ChunkSpan]:
        text = full_text[char_start:char_end]
        if not text.strip():
            return []

        words = list(re.finditer(r"\S+", text))
        if not words:
            return []

        spans: list[ChunkSpan] = []
        max_tokens_soft = max(max_tokens, target_tokens)
        i = 0
        while i < len(words):
            start_word = i
            start_char = words[start_word].start()
            last_safe_char: int | None = None
            cut_word = start_word

            while cut_word < len(words):
                candidate_end = words[cut_word].end()
                candidate_text = text[start_char:candidate_end]
                candidate_tokens = estimate_tokens(candidate_text)
                if candidate_tokens > max_tokens_soft:
                    break

                safe_matches = list(
                    re.finditer(r"[.!?\u1362\u1367\u1368,;:\u2014\u2013\-](?:\s+|$)", candidate_text)
                )
                if safe_matches:
                    last_safe_char = start_char + safe_matches[-1].end()

                cut_word += 1

            if cut_word == start_word:
                # Single token too large; emit it as-is to avoid an infinite loop.
                end_char = words[start_word].end()
            else:
                end_char = words[cut_word - 1].end()
                if last_safe_char is not None and last_safe_char > start_char:
                    end_char = last_safe_char

            absolute_start = char_start + start_char
            absolute_end = char_start + end_char
            spans.append(
                ChunkSpan(
                    char_start=absolute_start,
                    char_end=absolute_end,
                    source_blocks=source_blocks,
                    mapping_method=mapping_method,
                    mapping_quality=mapping_quality,
                    close_reason=close_reason,
                )
            )

            while i < len(words) and words[i].end() <= end_char:
                i += 1

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
        close_reason: str,
    ) -> ChunkSpan | None:
        if char_start is None or char_end is None:
            return None
        char_start = max(0, int(char_start))
        char_end = min(len(full_text), int(char_end))
        if char_end <= char_start:
            return None

        # Keep the span bounded at the last safe boundary inside the current window.
        char_end = self._trim_end_to_safe_boundary(full_text, char_start, char_end)

        return ChunkSpan(
            char_start=char_start,
            char_end=char_end,
            source_blocks=blocks,
            mapping_method=mapping_method,
            mapping_quality=float(mapping_quality),
            close_reason=close_reason,
        )

    def _trim_end_to_safe_boundary(self, full_text: str, start: int, end: int, max_backtrack: int = 800) -> int:
        text = full_text
        if not text or end <= start:
            return end

        tail = text[max(start, end - 3) : end]
        if re.search(r"[.!?\u1362\u1367\u1368]\s*$", tail):
            return end

        back_start = max(start, end - max_backtrack)
        back_text = text[back_start:end]
        matches = list(re.finditer(r"([.!?\u1362\u1367\u1368,;:\u2014\u2013\-])(?:\s+|$)", back_text))
        if matches:
            last = matches[-1]
            new_end = back_start + last.end()
            if new_end > start:
                return new_end

        return end

    def _dedupe_and_sort_spans(self, spans: list[ChunkSpan], full_text: str | None) -> list[ChunkSpan]:
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
        # Repair boundaries to avoid splitting sentences across adjacent spans.
        self._repair_spans_to_sentence_boundaries(deduped, full_text=full_text)
        return deduped

    def _repair_spans_to_sentence_boundaries(self, spans: list[ChunkSpan], full_text: str | None, max_lookahead: int = 800) -> None:
        if not spans or not full_text:
            return
        boundary_pattern = re.compile(r"([.!?\u1362\u1367\u1368,;:\u2014\u2013\-])(?:\s+|$)")
        for i in range(len(spans) - 1):
            cur = spans[i]
            nxt = spans[i + 1]
            if cur.char_end <= cur.char_start or nxt.char_end <= nxt.char_start:
                continue

            tail = full_text[max(cur.char_start, cur.char_end - 3) : cur.char_end]
            if boundary_pattern.search(tail):
                continue

            back_start = max(cur.char_start, cur.char_end - max_lookahead)
            back_text = full_text[back_start:cur.char_end]
            matches = list(boundary_pattern.finditer(back_text))
            if matches:
                last = matches[-1]
                new_end = back_start + last.end()
                if new_end > cur.char_start and new_end <= nxt.char_start:
                    new_cur = ChunkSpan(
                        char_start=cur.char_start,
                        char_end=new_end,
                        source_blocks=cur.source_blocks,
                        mapping_method=cur.mapping_method,
                        mapping_quality=cur.mapping_quality,
                        close_reason=cur.close_reason,
                    )
                    new_nxt = ChunkSpan(
                        char_start=new_end,
                        char_end=nxt.char_end,
                        source_blocks=nxt.source_blocks,
                        mapping_method=nxt.mapping_method,
                        mapping_quality=nxt.mapping_quality,
                        close_reason=nxt.close_reason,
                    )
                    spans[i] = new_cur
                    spans[i + 1] = new_nxt
                    continue


def compute_chunk_quality(*, text: str, mapping_quality: float = 1.0, target_tokens: int = DEFAULT_TARGET_TOKENS) -> float:
    """Heuristic quality score [0..1] for a chunk: combines sentence completeness,
    mapping quality, and size relative to target tokens.
    """
    t = (text or "").strip()
    if not t:
        return 0.0

    tokens = estimate_tokens(t)
    length_score = min(1.0, tokens / max(1, target_tokens))

    # Sentence completeness: 1.0 if ends with sentence terminator, 0.5 otherwise
    completeness = 1.0 if re.search(r"[.!?\u1362\u1367\u1368]\s*$", t) else 0.5

    mq = float(mapping_quality or 0.0)

    # Weighted combination
    score = (0.5 * completeness) + (0.3 * length_score) + (0.2 * mq)
    score = max(0.0, min(1.0, score))
    return round(score, 4)



def estimate_tokens(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0

    words = len(re.findall(r"\S+", normalized))
    if words:
        return int(math.ceil(words * 1.10))
    return max(1, int(math.ceil(len(normalized) / 4)))
