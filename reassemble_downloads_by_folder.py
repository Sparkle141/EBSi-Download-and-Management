from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PIPELINE_RUNNER = ROOT / "test_crawl_and_reassemble" / "system" / "pipeline_runner.py"
OUTPUT_SUFFIX = "전사 및 조립"
SKIP_DIR_MARKERS = {OUTPUT_SUFFIX, "legacy"}


def should_skip(path: Path) -> bool:
    return any(marker in part for part in path.parts for marker in SKIP_DIR_MARKERS)


def discover_pdf_folders(input_dir: Path) -> list[Path]:
    folders: set[Path] = set()
    for pdf in input_dir.rglob("*.pdf"):
        if should_skip(pdf.relative_to(input_dir)):
            continue
        folders.add(pdf.parent)
    return sorted(folders, key=lambda item: item.as_posix())


def output_dir_for(folder: Path) -> Path:
    label = folder.name if folder.name else "다운로드"
    return folder / f"{label} {OUTPUT_SUFFIX}"


def run_reassembly(folder: Path, output_dir: Path, no_install_packages: bool) -> int:
    command = [
        sys.executable,
        str(PIPELINE_RUNNER),
        "--input",
        str(folder),
        "--output-dir",
        str(output_dir),
    ]
    if no_install_packages:
        command.append("--no-install-packages")
    print(f"[전사 및 조립] {folder} -> {output_dir}")
    completed = subprocess.run(command, cwd=ROOT)
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="다운로드 시험 폴더별로 전사 및 재조립 산출물을 옆에 생성합니다.")
    parser.add_argument("--input-dir", required=True, help="downloads/<과목>/current 폴더")
    parser.add_argument("--manifest", default="", help="처리 결과 JSON 기록")
    parser.add_argument("--no-install-packages", action="store_true", help="패키지 자동 설치를 건너뜁니다.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = ROOT / input_dir
    if not input_dir.exists():
        raise SystemExit(f"다운로드 원본 폴더가 없습니다: {input_dir}")
    if not PIPELINE_RUNNER.exists():
        raise SystemExit(f"전사/재조립 실행기를 찾을 수 없습니다: {PIPELINE_RUNNER}")

    folders = discover_pdf_folders(input_dir)
    if not folders:
        raise SystemExit(f"전사할 PDF가 없습니다: {input_dir}")

    results: list[dict[str, object]] = []
    failures = 0
    for folder in folders:
        output_dir = output_dir_for(folder)
        code = run_reassembly(folder, output_dir, args.no_install_packages)
        if code != 0:
            failures += 1
        results.append(
            {
                "input_folder": str(folder),
                "output_folder": str(output_dir),
                "exit_code": code,
            }
        )

    manifest = {
        "schema": "download-folder-reassembly-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "folder_count": len(folders),
        "failure_count": failures,
        "results": results,
    }
    manifest_path = Path(args.manifest) if args.manifest else input_dir / "reassembly_manifest.json"
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"처리 폴더: {len(folders)}개")
    print(f"실패: {failures}개")
    print(f"기록: {manifest_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
