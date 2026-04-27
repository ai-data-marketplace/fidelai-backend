from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class LayoutAnalysisResult:
    structured_blocks: list[dict[str, Any]]
    layout_metadata: dict[str, Any]
    ordered_text: str


class LayoutAnalysisService:
    """Reconstructs document structure and assigns reading order."""
    def reconstruct_reading_order(self, extracted_pages):
        return sorted(extracted_pages, key=lambda item: item.get("page", 0))

    def _classify_block(self, block: dict[str, Any]) -> str:
        text = str(block.get("text", "")).strip()
        if not text:
            return "noise"
        declared = block.get("type")
        if declared in {"heading", "list_item", "paragraph", "table", "word", "caption"}:
            return declared
        # quick heuristics
        low_conf = float(block.get("confidence") or 0.0) < 0.3
        if low_conf and len(text) < 20:
            return "noise"
        # list detection
        if text.lstrip().startswith(("-", "•", "*")) or text.strip().split()[0].rstrip(".").isdigit():
            return "list_item"
        # table-ish detection (pipes, many short cells, tabs)
        if "|" in text or "\t" in text or (text.count(" ") < max(5, len(text) // 10) and "\n" in text):
            return "table"
        # caption detection
        lower = text.lower()
        if lower.startswith(("fig", "figure", "table")) or lower.endswith("caption"):
            return "caption"
        # heading heuristics
        words = text.split()
        if (len(words) <= 6 and text.endswith(":")) or (len(words) <= 5 and text.isupper()):
            return "heading"
        if len(words) <= 5:
            return "heading"
        return "paragraph"

    def _detect_columns_for_page(self, page: dict[str, Any]) -> dict[str, Any]:
        """Detect simple column layout based on block bbox centers.

        Returns a small metadata dict: {"detected_columns": int, "page_width": float}
        """
        centers = []
        max_right = 0.0
        for b in page.get("blocks", []):
            bbox = b.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            x0, y0, x1, y1 = bbox
            centers.append((x0 + x1) / 2.0)
            max_right = max(max_right, x1)

        if not centers or max_right <= 0:
            return {"detected_columns": 1, "page_width": max_right}

        centers.sort()
        # find largest normalized gap between adjacent centers
        gaps = []
        for i in range(1, len(centers)):
            gaps.append(centers[i] - centers[i - 1])
        largest_gap = max(gaps) if gaps else 0.0
        norm_gap = largest_gap / max_right if max_right else 0.0
        # threshold: if largest gap occupies significant portion, treat as two columns
        if norm_gap > 0.28:
            # crude estimate: two columns if large gap
            return {"detected_columns": 2, "page_width": max_right}
        # try three-column detection: look for two large gaps
        large_gaps = [g for g in gaps if (g / max_right) > 0.2]
        if len(large_gaps) >= 2:
            return {"detected_columns": 3, "page_width": max_right}
        return {"detected_columns": 1, "page_width": max_right}

    def build_structure(self, pages) -> LayoutAnalysisResult:
        ordered_pages = self.reconstruct_reading_order(pages)
        structured_pages: list[dict[str, Any]] = []
        ordered_text_parts: list[str] = []
        block_counts: list[int] = []
        page_confidences: list[float] = []

        for page in ordered_pages:
            page_blocks: list[dict[str, Any]] = []
            for block in page.get("blocks", []):
                block_type = self._classify_block(block)
                if block_type == "noise":
                    continue
                normalized_block = {
                    "type": block_type,
                    "text": str(block.get("text", "")).strip(),
                    "confidence": float(block.get("confidence", 0.0) or 0.0),
                }
                if block.get("bbox") is not None:
                    normalized_block["bbox"] = block.get("bbox")
                page_blocks.append(normalized_block)
                if normalized_block["text"]:
                    ordered_text_parts.append(normalized_block["text"])

            block_counts.append(len(page_blocks))
            page_confidences.append(float(page.get("confidence", 0.0) or 0.0))
            structured_pages.append({"page": page.get("page"), "blocks": page_blocks})

        layout_metadata = {
            "page_count": len(structured_pages),
            "block_counts": block_counts,
            "page_confidence": mean(page_confidences) if page_confidences else 0.0,
            "detected_columns": 1,
            "layout_model_confidence": mean(page_confidences) if page_confidences else 0.0,
            "noise_regions": [],
        }
        return LayoutAnalysisResult(
            structured_blocks=structured_pages,
            layout_metadata=layout_metadata,
            ordered_text="\n".join(ordered_text_parts).strip(),
        )