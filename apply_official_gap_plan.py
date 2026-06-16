from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


DEFAULT_TARGET_ROOT = (
    r"C:\Users\Dell\iCloudDrive\수능및모의고사문제\생활과 윤리 및 윤리와 사상\생활과 윤리"
    r"\[평가원]평가원 모의고사 생윤\[공식]평가원 개별파일 생윤 2014-2026"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_unique_source_paths(rows: list[dict[str, str]]) -> list[tuple[dict[str, str], Path]]:
    seen: set[Path] = set()
    result: list[tuple[dict[str, str], Path]] = []
    for row in rows:
        for raw_path in row.get("ready_to_copy_paths", "").split(";"):
            raw_path = raw_path.strip()
            if not raw_path:
                continue
            path = Path(raw_path)
            if path not in seen:
                seen.add(path)
                result.append((row, path))
    return result


def destination_for(target_root: Path, row: dict[str, str], source: Path) -> Path:
    academic_year = f"{row['academic_year']}학년도"
    session = row["session"]
    return target_root / academic_year / session / source.name


def build_plan(gap_plan: Path, target_root: Path) -> list[dict[str, str]]:
    rows = read_csv(gap_plan)
    plan: list[dict[str, str]] = []
    for row, source in iter_unique_source_paths(rows):
        destination = destination_for(target_root, row, source)
        source_exists = source.exists()
        destination_exists = destination.exists()
        source_sha256 = sha256_file(source) if source_exists else ""
        destination_sha256 = sha256_file(destination) if destination_exists else ""

        if not source_exists:
            action = "missing_source"
        elif destination_exists and source_sha256 == destination_sha256:
            action = "skip_same_file"
        elif destination_exists:
            action = "blocked_existing_different_file"
        else:
            action = "copy"

        plan.append(
            {
                "academic_year": row["academic_year"],
                "session": row["session"],
                "source": str(source),
                "destination": str(destination),
                "source_sha256": source_sha256,
                "destination_sha256": destination_sha256,
                "action": action,
            }
        )
    return plan


def apply_plan(plan: list[dict[str, str]]) -> None:
    for item in plan:
        if item["action"] != "copy":
            continue
        source = Path(item["source"])
        destination = Path(item["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_manifest(path: Path, plan: list[dict[str, str]], applied: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for item in plan:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    payload = {
        "applied": applied,
        "counts": counts,
        "items": plan,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공식 보강 계획표를 원본 iCloud 폴더에 반영합니다.")
    parser.add_argument("--gap-plan", default="reports/official_gap_plan_2014_2026.csv")
    parser.add_argument("--target-root", default=DEFAULT_TARGET_ROOT)
    parser.add_argument("--manifest", default="reports/official_gap_apply_manifest.json")
    parser.add_argument("--apply", action="store_true", help="실제 파일 복사를 수행합니다.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = build_plan(Path(args.gap_plan), Path(args.target_root))
    blocked = [item for item in plan if item["action"].startswith("blocked") or item["action"] == "missing_source"]
    if args.apply and blocked:
        write_manifest(Path(args.manifest), plan, applied=False)
        raise SystemExit(f"복사를 중단했습니다. 처리 불가 항목 {len(blocked)}개가 있습니다.")
    if args.apply:
        apply_plan(plan)
    write_manifest(Path(args.manifest), plan, applied=args.apply)

    counts: dict[str, int] = {}
    for item in plan:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    print(f"대상 파일: {len(plan)}개")
    for action, count in sorted(counts.items()):
        print(f"{action}: {count}개")
    print(f"반영 여부: {'yes' if args.apply else 'no'}")
    print(f"기록: {args.manifest}")


if __name__ == "__main__":
    main()
