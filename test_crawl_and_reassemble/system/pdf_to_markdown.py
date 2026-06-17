from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from filename_meta import parse_exam_metadata, safe_path_part

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


QUESTION_START_RE = re.compile(r"^\s*\d{1,2}\s*\.")
ASSET_PLACEHOLDER_RE = re.compile(r"^(\[(그림|표|스캔 이미지|스캔 페이지)\s*\d+\]\s*)+$")
SCAN_PAGE_IMAGE_RATIO = 0.75
SPARSE_TEXT_WORD_THRESHOLD = 20
SPARSE_TEXT_CHAR_THRESHOLD = 80
LARGE_IMAGE_RATIO_FOR_FALLBACK = 0.35


@dataclass
class TextItem:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    item_type: str = "word"
    asset_id: str | None = None

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class PageLayout:
    page_no: int
    page_width: float
    page_height: float
    is_two_column: bool
    mid_x: float
    body_top: float | None
    left_items: int
    right_items: int
    full_width_items: int
    placeholders: int
    text_items: int = 0
    text_chars: int = 0
    largest_image_ratio: float = 0.0
    difficult_page: bool = False
    fallback_reason: str | None = None
    fallback_asset_id: str | None = None


@dataclass
class AssetRecord:
    asset_id: str
    label: str
    kind: str
    page_no: int
    bbox: list[float]
    file: str | None
    width: float
    height: float


@dataclass
class TextLineRecord:
    text: str
    page_no: int
    bbox: list[float]
    column: str
    region: str
    asset_id: str | None = None
    asset_label: str | None = None


def discover_pdfs(input_path: Path, pattern: str) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".pdf" else []
    return sorted(p for p in input_path.rglob(pattern) if p.is_file() and p.suffix.lower() == ".pdf")


def safe_output_path(pdf_path: Path, input_root: Path, output_root: Path) -> Path:
    if input_root.is_file():
        rel_parent = Path(".")
    else:
        try:
            rel_parent = pdf_path.parent.relative_to(input_root)
        except ValueError:
            rel_parent = Path(".")
    return output_root / rel_parent / f"{safe_path_part(pdf_path.stem)}.md"


def word_to_item(word: dict) -> TextItem:
    return TextItem(
        text=str(word.get("text", "")),
        x0=float(word.get("x0", 0)),
        x1=float(word.get("x1", 0)),
        top=float(word.get("top", 0)),
        bottom=float(word.get("bottom", 0)),
        item_type="word",
    )


def bbox_to_item(
    label: str,
    bbox: tuple[float, float, float, float],
    item_type: str,
    asset_id: str | None = None,
) -> TextItem:
    x0, top, x1, bottom = bbox
    return TextItem(
        text=label,
        x0=float(x0),
        x1=float(x1),
        top=float(top),
        bottom=float(bottom),
        item_type=item_type,
        asset_id=asset_id,
    )


def collect_placeholders(
    page,
    include_placeholders: bool,
    asset_output_dir: Path | None,
    image_counter: list[int],
    table_counter: list[int],
    assets: list[AssetRecord],
) -> list[TextItem]:
    if not include_placeholders:
        return []

    items: list[TextItem] = []

    try:
        for image in page.images:
            x0 = float(image.get("x0", 0))
            x1 = float(image.get("x1", 0))
            top = float(image.get("top", 0))
            bottom = float(image.get("bottom", top))
            width = max(x1 - x0, 0)
            height = max(bottom - top, 0)
            page_area = max(float(page.width) * float(page.height), 1)
            if width * height / page_area > SCAN_PAGE_IMAGE_RATIO:
                kind = "scan_page"
                image_counter[0] += 1
                asset_id = f"image_{image_counter[0]:03d}"
                label = f"[스캔 이미지 {image_counter[0]}]"
            else:
                kind = "image"
                image_counter[0] += 1
                asset_id = f"image_{image_counter[0]:03d}"
                label = f"[그림 {image_counter[0]}]"
            file_path = save_page_crop(page, (x0, top, x1, bottom), asset_output_dir, "images", asset_id)
            assets.append(make_asset_record(asset_id, label, kind, page, (x0, top, x1, bottom), file_path))
            items.append(TextItem(label, x0, x1, top, bottom, "image", asset_id))
    except Exception:
        pass

    try:
        for table in page.find_tables() or []:
            bbox = getattr(table, "bbox", None)
            if bbox:
                x0, top, x1, bottom = [float(v) for v in bbox]
                if (x1 - x0) < 20 or (bottom - top) < 10:
                    continue
                table_counter[0] += 1
                asset_id = f"table_{table_counter[0]:03d}"
                label = f"[표 {table_counter[0]}]"
                clean_bbox = (x0, top, x1, bottom)
                file_path = save_page_crop(page, clean_bbox, asset_output_dir, "tables", asset_id)
                assets.append(make_asset_record(asset_id, label, "table", page, clean_bbox, file_path))
                items.append(bbox_to_item(label, clean_bbox, "table", asset_id))
    except Exception:
        pass

    return merge_near_placeholders(items)


def largest_image_ratio(page) -> float:
    page_area = max(float(page.width) * float(page.height), 1)
    ratios: list[float] = []
    try:
        for image in page.images:
            x0 = float(image.get("x0", 0))
            x1 = float(image.get("x1", 0))
            top = float(image.get("top", 0))
            bottom = float(image.get("bottom", top))
            ratios.append(max(x1 - x0, 0) * max(bottom - top, 0) / page_area)
    except Exception:
        return 0.0
    return max(ratios, default=0.0)


def detect_fallback_reason(layout: PageLayout) -> str | None:
    has_page_scan = layout.largest_image_ratio > SCAN_PAGE_IMAGE_RATIO
    has_large_image = layout.largest_image_ratio > LARGE_IMAGE_RATIO_FOR_FALLBACK
    sparse_words = layout.text_items < SPARSE_TEXT_WORD_THRESHOLD
    sparse_chars = layout.text_chars < SPARSE_TEXT_CHAR_THRESHOLD

    if layout.text_items == 0:
        return "no_text_layer"
    if has_page_scan:
        return "page_scan_image"
    if has_large_image and (sparse_words or sparse_chars):
        return "sparse_text_with_large_image"
    return None


def save_page_screenshot(
    page,
    asset_output_dir: Path | None,
    scan_counter: list[int],
) -> AssetRecord | None:
    if asset_output_dir is None:
        return None

    scan_counter[0] += 1
    asset_id = f"scan_{scan_counter[0]:03d}"
    label = f"[스캔 페이지 {int(page.page_number)}]"
    out_dir = asset_output_dir / "scans"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{asset_id}_p{int(page.page_number):02d}.png"
    try:
        page.to_image(resolution=180).save(out_path, format="PNG")
    except Exception:
        return None

    return make_asset_record(
        asset_id=asset_id,
        label=label,
        kind="page_screenshot",
        page=page,
        bbox=(0, 0, float(page.width), float(page.height)),
        file_path=out_path,
    )


def make_asset_record(
    asset_id: str,
    label: str,
    kind: str,
    page,
    bbox: tuple[float, float, float, float],
    file_path: Path | None,
) -> AssetRecord:
    x0, top, x1, bottom = bbox
    return AssetRecord(
        asset_id=asset_id,
        label=label.strip("[]"),
        kind=kind,
        page_no=int(page.page_number),
        bbox=[round(x0, 3), round(top, 3), round(x1, 3), round(bottom, 3)],
        file=str(file_path) if file_path else None,
        width=round(x1 - x0, 3),
        height=round(bottom - top, 3),
    )


def save_page_crop(
    page,
    bbox: tuple[float, float, float, float],
    asset_output_dir: Path | None,
    group: str,
    asset_id: str,
) -> Path | None:
    if asset_output_dir is None:
        return None

    x0, top, x1, bottom = clamp_bbox(bbox, float(page.width), float(page.height), padding=3)
    if x1 <= x0 or bottom <= top:
        return None

    out_dir = asset_output_dir / group
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{asset_id}_p{int(page.page_number):02d}.png"
    try:
        crop = page.crop((x0, top, x1, bottom))
        crop.to_image(resolution=180).save(out_path, format="PNG")
        return out_path
    except Exception:
        return None


def clamp_bbox(
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    padding: float,
) -> tuple[float, float, float, float]:
    x0, top, x1, bottom = bbox
    return (
        max(0, x0 - padding),
        max(0, top - padding),
        min(page_width, x1 + padding),
        min(page_height, bottom + padding),
    )


def merge_near_placeholders(items: list[TextItem]) -> list[TextItem]:
    if not items:
        return []
    items = sorted(items, key=lambda item: (item.top, item.x0))
    merged: list[TextItem] = []
    for item in items:
        if not merged:
            merged.append(item)
            continue
        prev = merged[-1]
        same_label = prev.text == item.text
        close_y = abs(prev.top - item.top) < 8 or abs(prev.bottom - item.bottom) < 8
        overlap_x = min(prev.x1, item.x1) - max(prev.x0, item.x0) > -8
        if same_label and close_y and overlap_x:
            prev.x0 = min(prev.x0, item.x0)
            prev.x1 = max(prev.x1, item.x1)
            prev.top = min(prev.top, item.top)
            prev.bottom = max(prev.bottom, item.bottom)
        else:
            merged.append(item)
    return merged


def detect_two_columns(words: list[TextItem], page_width: float) -> bool:
    if len(words) < 40:
        return False
    mid = page_width / 2
    left = sum(1 for word in words if word.cx < mid - page_width * 0.06)
    right = sum(1 for word in words if word.cx > mid + page_width * 0.06)
    if min(left, right) < 15:
        return False
    ratio = min(left, right) / max(left, right)
    return ratio > 0.25


def detect_body_top(words: list[TextItem]) -> float | None:
    candidates = [
        word.top
        for word in words
        if QUESTION_START_RE.match(word.text) or re.match(r"^\d{1,2}\s*\.$", word.text)
    ]
    if not candidates:
        return None
    return max(min(candidates) - 12, 0)


def split_page_items(
    page,
    line_tolerance: float,
    include_placeholders: bool,
    asset_output_dir: Path | None,
    image_counter: list[int],
    table_counter: list[int],
    assets: list[AssetRecord],
) -> tuple[list[TextItem], list[TextItem], list[TextItem], PageLayout]:
    words_raw = page.extract_words(
        x_tolerance=1.5,
        y_tolerance=line_tolerance,
        keep_blank_chars=False,
        use_text_flow=False,
    )
    words = [word_to_item(word) for word in words_raw if str(word.get("text", "")).strip()]
    placeholders = collect_placeholders(
        page,
        include_placeholders,
        asset_output_dir,
        image_counter,
        table_counter,
        assets,
    )

    page_width = float(page.width)
    page_height = float(page.height)
    mid_x = page_width / 2
    is_two_column = detect_two_columns(words, page_width)
    body_top = detect_body_top(words) if is_two_column else None
    text_chars = sum(len(word.text) for word in words)
    image_ratio = largest_image_ratio(page)

    if not is_two_column:
        items = sorted(words + placeholders, key=lambda item: (item.top, item.x0))
        layout = PageLayout(
            page_no=int(page.page_number),
            page_width=page_width,
            page_height=page_height,
            is_two_column=False,
            mid_x=mid_x,
            body_top=None,
            left_items=len(items),
            right_items=0,
            full_width_items=0,
            placeholders=len(placeholders),
            text_items=len(words),
            text_chars=text_chars,
            largest_image_ratio=round(image_ratio, 4),
        )
        return [], items, [], layout

    full_width: list[TextItem] = []
    left: list[TextItem] = []
    right: list[TextItem] = []

    for item in words + placeholders:
        if body_top is not None and item.bottom < body_top:
            full_width.append(item)
        elif item.cx < mid_x:
            left.append(item)
        else:
            right.append(item)

    layout = PageLayout(
        page_no=int(page.page_number),
        page_width=page_width,
        page_height=page_height,
        is_two_column=True,
        mid_x=mid_x,
        body_top=body_top,
        left_items=len(left),
        right_items=len(right),
        full_width_items=len(full_width),
        placeholders=len(placeholders),
        text_items=len(words),
        text_chars=text_chars,
        largest_image_ratio=round(image_ratio, 4),
    )
    return (
        sorted(full_width, key=lambda item: (item.top, item.x0)),
        sorted(left, key=lambda item: (item.top, item.x0)),
        sorted(right, key=lambda item: (item.top, item.x0)),
        layout,
    )


def group_lines(items: list[TextItem], y_tolerance: float) -> list[list[TextItem]]:
    lines: list[list[TextItem]] = []
    current: list[TextItem] = []
    current_top: float | None = None

    for item in sorted(items, key=lambda x: (x.top, x.x0)):
        if current_top is None or abs(item.top - current_top) <= y_tolerance:
            current.append(item)
            if current_top is None:
                current_top = item.top
            else:
                current_top = (current_top * (len(current) - 1) + item.top) / len(current)
        else:
            lines.append(sorted(current, key=lambda x: x.x0))
            current = [item]
            current_top = item.top

    if current:
        lines.append(sorted(current, key=lambda x: x.x0))
    return lines


def line_to_text(line: list[TextItem]) -> str:
    tokens = [item.text.strip() for item in line if item.text.strip()]
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.:;?!\]\)])", r"\1", text)
    text = re.sub(r"([\[\(])\s+", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_asset_placeholder_text(text: str) -> bool:
    return bool(ASSET_PLACEHOLDER_RE.match(text.strip()))


def item_bbox(items: list[TextItem]) -> list[float]:
    return [
        round(min(item.x0 for item in items), 3),
        round(min(item.top for item in items), 3),
        round(max(item.x1 for item in items), 3),
        round(max(item.bottom for item in items), 3),
    ]


def bbox_area(bbox: list[float]) -> float:
    return max(bbox[2] - bbox[0], 0) * max(bbox[3] - bbox[1], 0)


def bbox_intersection_area(a: list[float], b: list[float]) -> float:
    width = max(min(a[2], b[2]) - max(a[0], b[0]), 0)
    height = max(min(a[3], b[3]) - max(a[1], b[1]), 0)
    return width * height


def bbox_center_inside(inner: list[float], outer: list[float]) -> bool:
    cx = (inner[0] + inner[2]) / 2
    cy = (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def asset_region(assets: list[AssetRecord]) -> str:
    kinds = {asset.kind for asset in assets}
    if len(kinds) != 1:
        return "asset"
    kind = next(iter(kinds))
    if kind == "table":
        return "table"
    if kind in {"image", "scan_page", "page_screenshot"}:
        return "image"
    return "asset"


def classify_line_assets(
    line: list[TextItem],
    line_bbox: list[float],
    assets_by_id: dict[str, AssetRecord],
    page_assets: list[AssetRecord],
) -> list[AssetRecord]:
    direct: list[AssetRecord] = []
    seen: set[str] = set()
    for item in line:
        if item.asset_id and item.asset_id in assets_by_id and item.asset_id not in seen:
            direct.append(assets_by_id[item.asset_id])
            seen.add(item.asset_id)
    if direct:
        return direct

    line_area = max(bbox_area(line_bbox), 1)
    scored: list[tuple[float, AssetRecord]] = []
    for asset in page_assets:
        overlap = bbox_intersection_area(line_bbox, asset.bbox)
        ratio = overlap / line_area
        if ratio >= 0.15 or bbox_center_inside(line_bbox, asset.bbox):
            scored.append((ratio, asset))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [scored[0][1]] if scored else []


def make_text_line_record(
    line: list[TextItem],
    text: str,
    page_no: int,
    column: str,
    default_region: str,
    assets_by_id: dict[str, AssetRecord],
    page_assets: list[AssetRecord],
) -> TextLineRecord:
    bbox = item_bbox(line)
    matched_assets = classify_line_assets(line, bbox, assets_by_id, page_assets)
    if matched_assets:
        return TextLineRecord(
            text=text,
            page_no=page_no,
            bbox=bbox,
            column=column,
            region=asset_region(matched_assets),
            asset_id=", ".join(asset.asset_id for asset in matched_assets),
            asset_label=", ".join(asset.label for asset in matched_assets),
        )

    return TextLineRecord(
        text=text,
        page_no=page_no,
        bbox=bbox,
        column=column,
        region=default_region,
    )


def render_items(
    items: list[TextItem],
    y_tolerance: float,
    blank_before_question: bool,
    page_no: int | None = None,
    column: str = "page",
    default_region: str = "body",
    assets_by_id: dict[str, AssetRecord] | None = None,
    page_assets: list[AssetRecord] | None = None,
    line_records: list[TextLineRecord] | None = None,
) -> list[str]:
    output: list[str] = []
    for line in group_lines(items, y_tolerance):
        text = line_to_text(line)
        if not text:
            continue
        if blank_before_question and QUESTION_START_RE.match(text) and output and output[-1] != "":
            output.append("")
        output.append(text)
        if line_records is not None and page_no is not None:
            line_records.append(
                make_text_line_record(
                    line=line,
                    text=text,
                    page_no=page_no,
                    column=column,
                    default_region=default_region,
                    assets_by_id=assets_by_id or {},
                    page_assets=page_assets or [],
                )
            )
    while output and output[-1] == "":
        output.pop()
    return output


def record_asset_ids(record: TextLineRecord) -> list[str]:
    if not record.asset_id:
        return []
    return [asset_id.strip() for asset_id in record.asset_id.split(",") if asset_id.strip()]


def record_has_asset_kind(
    record: TextLineRecord,
    assets_by_id: dict[str, AssetRecord],
    kinds: set[str],
) -> bool:
    for asset_id in record_asset_ids(record):
        asset = assets_by_id.get(asset_id)
        if asset and asset.kind in kinds:
            return True
    return False


def render_image_text_sections(
    page_records: list[TextLineRecord],
    assets_by_id: dict[str, AssetRecord],
) -> list[str]:
    groups: dict[str, list[TextLineRecord]] = {}
    for record in page_records:
        if record.region != "image":
            continue
        if is_asset_placeholder_text(record.text):
            continue
        if not record_has_asset_kind(record, assets_by_id, {"image"}):
            continue
        label = record.asset_label or record.asset_id or "그림"
        groups.setdefault(label, []).append(record)

    if not groups:
        return []

    output = ["", "### 그림에서 추출된 텍스트", ""]
    for label, records in groups.items():
        output.append(f"#### {label}")
        output.append("")
        for record in records:
            output.append(f"- {record.text}")
        output.append("")
    while output and output[-1] == "":
        output.pop()
    return output


def transcribe_pdf(
    pdf_path: Path,
    line_tolerance: float,
    include_placeholders: bool,
    blank_before_question: bool,
    debug_json: bool = False,
    asset_output_dir: Path | None = None,
    max_pages: int | None = None,
) -> tuple[str, list[PageLayout], list[AssetRecord], list[TextLineRecord]]:
    if not HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber가 필요합니다. `pip install -r requirements.txt`를 먼저 실행하세요.")

    meta = parse_exam_metadata(pdf_path)
    layouts: list[PageLayout] = []
    assets: list[AssetRecord] = []
    line_records: list[TextLineRecord] = []
    image_counter = [0]
    table_counter = [0]
    scan_counter = [0]
    lines: list[str] = []

    title = meta.stem
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"> source_file: {meta.filename}")
    if meta.subject_canonical or meta.year or meta.grade or meta.month:
        summary = []
        if meta.year:
            summary.append(f"{meta.year}년")
        if meta.grade:
            summary.append(f"고{meta.grade}")
        if meta.month:
            summary.append(f"{meta.month}월")
        if meta.subject_canonical:
            summary.append(meta.subject_canonical)
        lines.append(f"> inferred_meta: {' / '.join(summary)}")
    lines.append("")

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[:max_pages] if max_pages else pdf.pages
        for page_index, page in enumerate(pages, 1):
            page_line_start = len(line_records)
            full, left, right, layout = split_page_items(
                page,
                line_tolerance,
                include_placeholders,
                asset_output_dir,
                image_counter,
                table_counter,
                assets,
            )
            fallback_reason = detect_fallback_reason(layout)
            if fallback_reason:
                fallback_asset = save_page_screenshot(page, asset_output_dir, scan_counter)
                layout.difficult_page = True
                layout.fallback_reason = fallback_reason
                if fallback_asset:
                    assets.append(fallback_asset)
                    layout.fallback_asset_id = fallback_asset.asset_id
            layouts.append(layout)
            assets_by_id = {asset.asset_id: asset for asset in assets}
            page_assets = [asset for asset in assets if asset.page_no == page_index]

            lines.append(f"## Page {page_index}")
            lines.append("")
            if layout.difficult_page:
                fallback_label = None
                if layout.fallback_asset_id and layout.fallback_asset_id in assets_by_id:
                    fallback_label = assets_by_id[layout.fallback_asset_id].label
                if fallback_label:
                    lines.append(
                        f"> 스캔입니다. 텍스트 전사가 불완전할 수 있어 원본 페이지 스크린샷을 보존했습니다: [{fallback_label}]"
                    )
                else:
                    lines.append(
                        "> 스캔입니다. 텍스트 전사가 불완전할 수 있어 이 페이지는 검토가 필요합니다."
                    )
                lines.append(f"> fallback_reason: {layout.fallback_reason}")
                lines.append("")

            if layout.is_two_column:
                if full:
                    lines.append("### Full Width")
                    lines.append("")
                    lines.extend(
                        render_items(
                            full,
                            line_tolerance,
                            blank_before_question,
                            page_no=page_index,
                            column="full",
                            default_region="header_footer",
                            assets_by_id=assets_by_id,
                            page_assets=page_assets,
                            line_records=line_records,
                        )
                    )
                    lines.append("")
                lines.append("### Left Column")
                lines.append("")
                lines.extend(
                    render_items(
                        left,
                        line_tolerance,
                        blank_before_question,
                        page_no=page_index,
                        column="left",
                        default_region="body",
                        assets_by_id=assets_by_id,
                        page_assets=page_assets,
                        line_records=line_records,
                    )
                )
                lines.append("")
                lines.append("### Right Column")
                lines.append("")
                lines.extend(
                    render_items(
                        right,
                        line_tolerance,
                        blank_before_question,
                        page_no=page_index,
                        column="right",
                        default_region="body",
                        assets_by_id=assets_by_id,
                        page_assets=page_assets,
                        line_records=line_records,
                    )
                )
            else:
                lines.extend(
                    render_items(
                        left,
                        line_tolerance,
                        blank_before_question,
                        page_no=page_index,
                        column="page",
                        default_region="body",
                        assets_by_id=assets_by_id,
                        page_assets=page_assets,
                        line_records=line_records,
                    )
                )

            image_text_sections = render_image_text_sections(
                line_records[page_line_start:],
                assets_by_id,
            )
            if image_text_sections:
                lines.extend(image_text_sections)

            if page_index != len(pages):
                lines.append("")
                lines.append("---")
                lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines) + "\n", layouts, assets, line_records


def write_debug_json(path: Path, layouts: list[PageLayout]) -> None:
    data = [asdict(layout) for layout in layouts]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_assets_json(path: Path, assets: list[AssetRecord], base_dir: Path | None = None) -> None:
    data = []
    for asset in assets:
        row = asdict(asset)
        if base_dir and row.get("file"):
            try:
                row["file"] = str(Path(row["file"]).resolve().relative_to(base_dir.resolve()))
            except ValueError:
                pass
        data.append(row)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text_lines_json(path: Path, lines: list[TextLineRecord]) -> None:
    data = [asdict(line) for line in lines]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="수능·학평 PDF를 좌표 기반 마크다운 전사본으로 변환합니다. API 호출은 사용하지 않습니다."
    )
    parser.add_argument("--input", required=True, type=Path, help="PDF 파일 또는 PDF 루트 폴더")
    parser.add_argument("--output", default=Path("./markdown_output"), type=Path, help="마크다운 저장 폴더")
    parser.add_argument("--pattern", default="*.pdf", help="폴더 처리 시 재귀 탐색 패턴")
    parser.add_argument("--line-tolerance", type=float, default=3.0, help="같은 줄로 묶을 y좌표 허용값")
    parser.add_argument("--no-placeholders", action="store_true", help="[그림], [표] 자리표시를 생략")
    parser.add_argument("--no-assets", action="store_true", help="그림/표 PNG 추출을 생략")
    parser.add_argument("--no-blank-before-question", action="store_true", help="문항 번호 앞 빈 줄 삽입 생략")
    parser.add_argument("--overwrite", action="store_true", help="기존 md 파일이 있어도 다시 생성")
    parser.add_argument("--debug-json", action="store_true", help="페이지별 레이아웃 판정 JSON도 저장")
    parser.add_argument("--dry-run", action="store_true", help="처리 대상만 출력")
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N개만 처리")
    parser.add_argument("--max-pages", type=int, default=None, help="각 PDF에서 앞 N쪽만 시험 처리")
    args = parser.parse_args()

    input_path = args.input.expanduser()
    output_root = args.output.expanduser()

    if not input_path.exists():
        print(f"입력 경로가 없습니다: {input_path}", file=sys.stderr)
        return 2
    if not HAS_PDFPLUMBER:
        print("pdfplumber가 필요합니다. `pip install -r requirements.txt`를 먼저 실행하세요.", file=sys.stderr)
        return 2

    pdfs = discover_pdfs(input_path, args.pattern)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    print(f"처리 대상 PDF: {len(pdfs)}개")
    if args.dry_run:
        for pdf in pdfs:
            print(pdf)
        return 0

    ok = 0
    skipped = 0
    failed = 0
    output_root.mkdir(parents=True, exist_ok=True)

    for index, pdf in enumerate(pdfs, 1):
        out_path = safe_output_path(pdf, input_path, output_root)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not args.overwrite:
            skipped += 1
            print(f"[{index}/{len(pdfs)}] 건너뜀: {out_path}")
            continue
        print(f"[{index}/{len(pdfs)}] 전사: {pdf.name}")
        try:
            asset_dir = None if args.no_assets else out_path.with_suffix("") / "assets"
            markdown, layouts, assets, line_records = transcribe_pdf(
                pdf,
                line_tolerance=args.line_tolerance,
                include_placeholders=not args.no_placeholders,
                blank_before_question=not args.no_blank_before_question,
                debug_json=args.debug_json,
                asset_output_dir=asset_dir,
                max_pages=args.max_pages,
            )
            out_path.write_text(markdown, encoding="utf-8")
            if args.debug_json:
                write_debug_json(out_path.with_suffix(".layout.json"), layouts)
                write_assets_json(out_path.with_suffix(".assets.json"), assets, base_dir=out_path.parent)
                write_text_lines_json(out_path.with_suffix(".lines.json"), line_records)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"[실패] {pdf}: {exc}", file=sys.stderr)

    print("\n완료")
    print(f"  생성: {ok}")
    print(f"  건너뜀: {skipped}")
    print(f"  실패: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
