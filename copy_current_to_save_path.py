from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wanted(row: dict[str, str], only_keys: set[str]) -> bool:
    if not only_keys:
        return row.get("reachable") == "yes"
    key = f"{row['academic_year']}|{row['session']}|{row['doc_group']}"
    return key in only_keys and row.get("reachable") == "yes"


def build_source_path(download_dir: Path, row: dict[str, str]) -> Path:
    return download_dir / year_folder_name(row) / row["session"] / row["recommended_filename"]


def build_destination_path(target_root: Path, row: dict[str, str]) -> Path:
    return target_root / year_folder_name(row) / row["session"] / row["recommended_filename"]


def year_folder_name(row: dict[str, str]) -> str:
    academic_year = row["academic_year"]
    if row.get("recommended_filename", "").startswith(f"{academic_year}년-"):
        return f"{academic_year}년"
    return f"{academic_year}학년도"


def copy_rows(rows: list[dict[str, str]], download_dir: Path, target_root: Path, only_keys: set[str]) -> dict[str, object]:
    copied: list[dict[str, str]] = []
    skipped_same: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    for row in rows:
        if not wanted(row, only_keys):
            continue

        source = build_source_path(download_dir, row)
        destination = build_destination_path(target_root, row)

        if not source.exists():
            missing.append({"source": source.as_posix(), "reason": "downloaded source not found"})
            continue

        source_hash = sha256_file(source)
        if destination.exists():
            destination_hash = sha256_file(destination)
            if source_hash == destination_hash:
                skipped_same.append({"source": source.as_posix(), "destination": destination.as_posix(), "sha256": source_hash})
            else:
                blocked.append(
                    {
                        "source": source.as_posix(),
                        "destination": destination.as_posix(),
                        "source_sha256": source_hash,
                        "destination_sha256": destination_hash,
                        "reason": "different file already exists",
                    }
                )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append({"source": source.as_posix(), "destination": destination.as_posix(), "sha256": source_hash})

    return {
        "copied": copied,
        "skipped_same": skipped_same,
        "blocked": blocked,
        "missing": missing,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="current 다운로드 원본을 사용자가 지정한 저장 경로로 복사합니다.")
    parser.add_argument("--sources-report", required=True)
    parser.add_argument("--download-dir", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--manifest", default="reports/copy_current_to_save_path_manifest.json")
    parser.add_argument("--only-keys", nargs="*", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(Path(args.sources_report))
    result = copy_rows(rows, Path(args.download_dir), Path(args.target_root), set(args.only_keys))

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"복사: {len(result['copied'])}개")
    print(f"동일 파일 유지: {len(result['skipped_same'])}개")
    print(f"충돌 중단: {len(result['blocked'])}개")
    print(f"원본 없음: {len(result['missing'])}개")
    print(f"기록: {manifest_path}")

    if result["blocked"] or result["missing"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
