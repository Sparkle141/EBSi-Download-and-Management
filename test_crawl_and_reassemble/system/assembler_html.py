from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote


MARKER_RE = re.compile(r"\[(그림|표)\s*(\d+)\]")


@dataclass(frozen=True)
class TranscriptFiles:
    markdown: Path
    assets_json: Path


@dataclass(frozen=True)
class AssetRef:
    asset_id: str
    label: str
    kind: str
    page_no: int | None
    raw_file: str | None
    resolved_file: Path | None
    src: str | None
    width: float | None
    height: float | None

    @property
    def exists(self) -> bool:
        return self.resolved_file is not None and self.resolved_file.exists()


def find_transcript_files(result_dir: Path) -> TranscriptFiles:
    """Find the markdown transcript and assets index inside one result folder."""
    result_dir = Path(result_dir).expanduser().resolve()
    if not result_dir.is_dir():
        raise FileNotFoundError(f"결과 폴더가 없습니다: {result_dir}")

    markdown_files = sorted(
        p for p in result_dir.glob("*.md") if p.is_file() and not p.name.endswith(".assembled.md")
    )
    assets_files = sorted(p for p in result_dir.glob("*.assets.json") if p.is_file())

    if not markdown_files:
        raise FileNotFoundError(f".md 파일을 찾지 못했습니다: {result_dir}")
    if not assets_files:
        raise FileNotFoundError(f".assets.json 파일을 찾지 못했습니다: {result_dir}")

    for markdown_path in markdown_files:
        expected_assets = result_dir / f"{markdown_path.stem}.assets.json"
        if expected_assets in assets_files:
            return TranscriptFiles(markdown=markdown_path, assets_json=expected_assets)

    if len(markdown_files) == 1 and len(assets_files) == 1:
        return TranscriptFiles(markdown=markdown_files[0], assets_json=assets_files[0])

    markdown_names = ", ".join(p.name for p in markdown_files)
    assets_names = ", ".join(p.name for p in assets_files)
    raise ValueError(f"전사 파일 짝을 고를 수 없습니다. md={markdown_names}, assets={assets_names}")


def load_assets(result_dir: Path) -> list[AssetRef]:
    """Load asset metadata and resolve image/table file paths for HTML output."""
    result_dir = Path(result_dir).expanduser().resolve()
    files = find_transcript_files(result_dir)

    with files.assets_json.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if isinstance(data, dict):
        raw_assets = data.get("assets") or data.get("items") or []
    elif isinstance(data, list):
        raw_assets = data
    else:
        raise ValueError(f"지원하지 않는 assets.json 형식입니다: {files.assets_json}")

    assets: list[AssetRef] = []
    for item in raw_assets:
        if not isinstance(item, dict):
            continue

        kind = str(item.get("kind") or "").strip().lower()
        asset_id = str(item.get("asset_id") or "").strip()
        label = _normalize_label(item.get("label")) or _label_from_asset_id(asset_id, kind)
        raw_file = item.get("file")
        raw_file_text = str(raw_file).strip() if raw_file is not None else None
        resolved_file = _resolve_asset_file(result_dir, raw_file_text)
        src = _make_html_src(result_dir, resolved_file)

        assets.append(
            AssetRef(
                asset_id=asset_id,
                label=label,
                kind=kind,
                page_no=_as_int(item.get("page_no")),
                raw_file=raw_file_text,
                resolved_file=resolved_file,
                src=src,
                width=_as_float(item.get("width")),
                height=_as_float(item.get("height")),
            )
        )

    return assets


def replace_asset_markers(markdown_text: str, assets: Iterable[AssetRef]) -> str:
    """Escape transcript text and replace [그림 n]/[표 n] markers with HTML."""
    assets_by_label = {asset.label: asset for asset in assets if asset.label}
    escaped_text = html.escape(markdown_text, quote=False)

    def replace(match: re.Match[str]) -> str:
        label = f"{match.group(1)} {int(match.group(2))}"
        asset = assets_by_label.get(label)
        if asset is None:
            return _render_missing(label, "assets.json에 해당 항목이 없습니다.")
        if not asset.exists or not asset.src:
            detail = f"경로: {asset.raw_file}" if asset.raw_file else "경로 정보가 없습니다."
            return _render_missing(label, detail)
        return _render_asset(asset)

    return MARKER_RE.sub(replace, escaped_text)


def assemble_html(result_dir: Path) -> Path:
    """Create a review HTML file from one transcript result folder."""
    result_dir = Path(result_dir).expanduser().resolve()
    files = find_transcript_files(result_dir)
    assets = load_assets(result_dir)

    markdown_text = files.markdown.read_text(encoding="utf-8-sig")
    body_html = replace_asset_markers(markdown_text, assets)
    output_path = result_dir / f"{files.markdown.stem}.assembled.html"

    output_path.write_text(
        _render_document(title=files.markdown.stem, body_html=body_html, asset_count=len(assets)),
        encoding="utf-8",
    )
    return output_path


def _normalize_label(value: object) -> str:
    if value is None:
        return ""
    match = re.search(r"(그림|표)\s*(\d+)", str(value))
    if not match:
        return str(value).strip()
    return f"{match.group(1)} {int(match.group(2))}"


def _label_from_asset_id(asset_id: str, kind: str) -> str:
    prefix = "그림" if kind == "image" else "표" if kind == "table" else ""
    match = re.search(r"(\d+)$", asset_id)
    if prefix and match:
        return f"{prefix} {int(match.group(1))}"
    return asset_id


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_asset_file(result_dir: Path, raw_file: str | None) -> Path | None:
    if not raw_file:
        return None

    raw_file = raw_file.strip().strip('"')
    raw_path = Path(raw_file)
    candidates: list[Path] = []

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        normalized = _path_from_asset_value(raw_file)
        candidates.extend(
            [
                result_dir / normalized,
                result_dir / raw_path,
            ]
        )

        basename = _basename(raw_file)
        if basename:
            candidates.extend(
                [
                    result_dir / "assets" / "images" / basename,
                    result_dir / "assets" / "tables" / basename,
                ]
            )

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved

    basename = _basename(raw_file)
    if basename:
        matches = sorted(p for p in result_dir.rglob(basename) if p.is_file())
        if matches:
            return matches[0].resolve()

    return None


def _path_from_asset_value(value: str) -> Path:
    parts = [part for part in re.split(r"[\\/]+", value) if part]
    if not parts:
        return Path(value)
    drive_match = re.match(r"^[A-Za-z]:$", parts[0])
    if drive_match and len(parts) > 1:
        return Path(parts[0] + "\\", *parts[1:])
    return Path(*parts)


def _basename(value: str) -> str:
    parts = [part for part in re.split(r"[\\/]+", value.strip()) if part]
    return parts[-1] if parts else ""


def _make_html_src(result_dir: Path, resolved_file: Path | None) -> str | None:
    if resolved_file is None:
        return None

    try:
        relative = resolved_file.relative_to(result_dir)
        return quote(relative.as_posix(), safe="/._-~()%")
    except ValueError:
        return resolved_file.as_uri()


def _render_asset(asset: AssetRef) -> str:
    page = f" · p.{asset.page_no}" if asset.page_no else ""
    kind_class = "asset-table" if asset.kind == "table" else "asset-image"
    label = html.escape(asset.label)
    src = html.escape(asset.src or "", quote=True)
    alt = html.escape(asset.label, quote=True)
    return (
        f'<figure class="asset-slot {kind_class}" data-label="{label}">'
        f'<figcaption>[{label}]{page}</figcaption>'
        f'<img src="{src}" alt="{alt}" loading="lazy">'
        "</figure>"
    )


def _render_missing(label: str, detail: str) -> str:
    safe_label = html.escape(label)
    safe_detail = html.escape(detail)
    return (
        f'<span class="asset-slot asset-missing" data-label="{safe_label}">'
        f'<strong>파일 없음: {safe_label}</strong>'
        f'<small>{safe_detail}</small>'
        "</span>"
    )


def _render_document(title: str, body_html: str, asset_count: int) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} 검수용 HTML</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1f2933;
      --muted: #667085;
      --line: #d6dbe3;
      --paper: #ffffff;
      --bg: #eef2f7;
      --accent: #1f7a68;
      --warn-bg: #fff6db;
      --warn-line: #d99a14;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", Arial, sans-serif;
      line-height: 1.65;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
      padding: 12px 22px;
    }}
    header h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }}
    header p {{
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    main {{
      width: min(1120px, calc(100% - 28px));
      margin: 18px auto 36px;
      padding: 28px 34px;
      border: 1px solid var(--line);
      background: var(--paper);
      box-shadow: 0 10px 24px rgba(18, 38, 63, 0.08);
    }}
    .transcript {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 15px;
    }}
    .asset-slot {{
      display: block;
      width: fit-content;
      max-width: 100%;
      margin: 12px 0;
      white-space: normal;
    }}
    .asset-slot figcaption {{
      margin: 0 0 6px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
    }}
    .asset-slot img {{
      display: block;
      max-width: 100%;
      height: auto;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .asset-missing {{
      padding: 10px 12px;
      border: 1px solid var(--warn-line);
      background: var(--warn-bg);
      color: #5d4300;
      border-radius: 4px;
    }}
    .asset-missing strong,
    .asset-missing small {{
      display: block;
    }}
    .asset-missing small {{
      margin-top: 4px;
      color: #7a5b0a;
    }}
    @media print {{
      body {{ background: #fff; }}
      header {{ position: static; }}
      main {{
        width: 100%;
        margin: 0;
        border: 0;
        box-shadow: none;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{safe_title}</h1>
    <p>검수용 HTML · 에셋 {asset_count}개</p>
  </header>
  <main>
    <div class="transcript">{body_html}</div>
  </main>
</body>
</html>
"""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="전사 결과 폴더의 마커를 이미지/표 PNG로 조립해 HTML을 생성합니다.")
    parser.add_argument("result_dir", type=Path, help="전사 결과 폴더 경로")
    args = parser.parse_args(argv)

    try:
        output_path = assemble_html(args.result_dir)
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
