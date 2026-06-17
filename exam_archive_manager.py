from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = "downloads/생활과 윤리/current"

CRAWLING_PROVENANCE_ID = "019e1a50-b475-77b2-a7d9-0ecd53cc2ab8"
KICE_SESSIONS = ("6월", "9월", "수능")
KICE_DOC_GROUPS = ("문제", "정답해설")


@dataclass
class InventoryRow:
    rel_path: str
    full_path: str
    name: str
    extension: str
    size_bytes: int
    modified_time: str
    top_folder: str
    authority: str
    artifact_group: str
    provenance_id: str
    academic_year: str
    calendar_year: str
    month: str
    exam_round: str
    doc_type: str
    subject: str
    normalized_key: str
    content_hash: str


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def academic_year_from_match(raw: str) -> str:
    if len(raw) == 2:
        return f"20{raw}"
    return raw


def find_academic_year(text: str, authority: str) -> str:
    match = re.search(r"(?<!\d)(20\d{2}|\d{2})\s*학년도", text)
    if match:
        return academic_year_from_match(match.group(1))

    match = re.search(r"(?<!\d)(20\d{2}|\d{2})\s*년도", text)
    if match and authority == "평가원":
        return academic_year_from_match(match.group(1))

    match = re.search(r"(?<!\d)(\d{2})\s*학년", text)
    if match:
        return academic_year_from_match(match.group(1))

    return ""


def find_calendar_year(text: str) -> str:
    match = re.search(r"(?<!\d)(20\d{2})\s*년", text)
    return match.group(1) if match else ""


def find_month(text: str) -> str:
    match = re.search(r"(?<!\d)(10|[3-9])\s*월", text)
    if match:
        return f"{int(match.group(1))}월"

    compact = compact_text(text)
    match = re.search(r"(?<!\d)(?:20)?\d{2}[_\-. ]?(03|04|05|06|07|09|10)(?!\d)", compact)
    if match:
        return f"{int(match.group(1))}월"

    return ""


def find_exam_round(text: str) -> str:
    compact = compact_text(text)
    if "수능특강" in compact or "수능완성" in compact:
        return "EBS"
    if "대학수학능력시험" in compact or re.search(r"(?<![가-힣])수능(?![가-힣])", text):
        return "수능"
    if "예비" in compact:
        return "예비"
    month = find_month(text)
    return month


def classify_authority(rel_path: str, name: str) -> str:
    text = f"{rel_path}\\{name}"
    compact = compact_text(text)
    if "수능특강" in compact or "수능완성" in compact:
        return "EBS"
    if "평가원" in compact or "[평가원]" in text:
        return "평가원"
    if "교육청" in compact or "학평" in compact or "[학평]" in text:
        return "학평"
    return "미분류"


def classify_subject(text: str) -> str:
    compact = compact_text(text)
    if "생활과윤리" in compact or "사회생활과윤리" in compact or "생윤" in compact:
        return "생활과윤리"
    return "미분류"


def classify_doc_type(name: str, exam_round: str, extension: str) -> str:
    compact = compact_text(name)
    has_answer = "정답" in compact or "답지" in compact or "답안" in compact
    has_solution = "해설" in compact
    if has_answer and has_solution:
        return "정답해설"
    if has_answer:
        return "정답"
    if has_solution:
        return "해설"
    if "문제" in compact or "문항지" in compact or "문항" in compact:
        return "문제"
    if extension == ".pdf" and exam_round in {"6월", "9월", "수능", "3월", "4월", "5월", "7월", "10월"}:
        return "문제"
    return "미분류"


def classify_artifact_group(rel_path: str, name: str, extension: str) -> str:
    text = compact_text(f"{rel_path}\\{name}")
    if "수능특강" in text or "수능완성" in text:
        return "EBS교재"
    if "크롤" in text or extension in {".png", ".json", ".html"}:
        return "크롤링산출물"
    if extension in {".md", ".txt"}:
        return "텍스트추출물"
    if extension == ".docx":
        return "문서산출물"
    if "기출[" in text or "문제모음" in text or re.search(r"\d{4}~\d{4}", text):
        return "통합본"
    if extension == ".pdf":
        return "원본PDF"
    return "기타"


def provenance_id_for(artifact_group: str) -> str:
    if artifact_group == "크롤링산출물":
        return CRAWLING_PROVENANCE_ID
    return ""


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_files(root: Path, include_hash: bool) -> list[InventoryRow]:
    rows: list[InventoryRow] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        rel = path.relative_to(root)
        rel_text = str(rel)
        top_folder = rel.parts[0] if rel.parts else ""
        extension = path.suffix.lower()
        authority = classify_authority(rel_text, path.name)
        subject = classify_subject(rel_text)
        artifact_group = classify_artifact_group(rel_text, path.name, extension)
        exam_round = find_exam_round(path.name)
        doc_type = classify_doc_type(path.name, exam_round, extension)
        academic_year = find_academic_year(path.name, authority)
        calendar_year = find_calendar_year(path.name)
        month = find_month(path.name)
        stat = path.stat()
        normalized_key = "|".join(
            [
                authority,
                academic_year or "?",
                exam_round or "?",
                subject,
                doc_type,
                artifact_group,
            ]
        )

        rows.append(
            InventoryRow(
                rel_path=rel_text,
                full_path=str(path),
                name=path.name,
                extension=extension,
                size_bytes=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                top_folder=top_folder,
                authority=authority,
                artifact_group=artifact_group,
                provenance_id=provenance_id_for(artifact_group),
                academic_year=academic_year,
                calendar_year=calendar_year,
                month=month,
                exam_round=exam_round,
                doc_type=doc_type,
                subject=subject,
                normalized_key=normalized_key,
                content_hash=hash_file(path) if include_hash else "",
            )
        )
    impute_missing_academic_years(rows)
    return rows


def impute_missing_academic_years(rows: list[InventoryRow]) -> None:
    by_folder_round: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.academic_year:
            folder = str(Path(row.rel_path).parent)
            by_folder_round[(folder, row.authority, row.exam_round)].add(row.academic_year)

    for row in rows:
        if row.academic_year:
            continue
        folder = str(Path(row.rel_path).parent)
        years = by_folder_round.get((folder, row.authority, row.exam_round), set())
        if len(years) == 1:
            row.academic_year = next(iter(years))
            row.normalized_key = "|".join(
                [
                    row.authority,
                    row.academic_year or "?",
                    row.exam_round or "?",
                    row.subject,
                    row.doc_type,
                    row.artifact_group,
                ]
            )


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_inventory(out_dir: Path, rows: list[InventoryRow]) -> Path:
    path = out_dir / "inventory.csv"
    fieldnames = list(asdict(rows[0]).keys()) if rows else list(InventoryRow.__annotations__)
    write_csv(path, (asdict(row) for row in rows), fieldnames)
    return path


def duplicate_rows(rows: list[InventoryRow], use_hash: bool) -> list[dict[str, object]]:
    groups: dict[str, list[InventoryRow]] = defaultdict(list)
    for row in rows:
        if use_hash and row.content_hash:
            key = f"hash:{row.content_hash}"
        else:
            key = f"name-size:{compact_text(row.name)}:{row.size_bytes}"
        groups[key].append(row)

    output: list[dict[str, object]] = []
    for key, items in sorted(groups.items()):
        if len(items) <= 1:
            continue
        for item in items:
            output.append(
                {
                    "duplicate_key": key,
                    "count": len(items),
                    "rel_path": item.rel_path,
                    "size_bytes": item.size_bytes,
                    "authority": item.authority,
                    "artifact_group": item.artifact_group,
                    "doc_type": item.doc_type,
                }
            )
    return output


def write_duplicates(out_dir: Path, rows: list[InventoryRow], use_hash: bool) -> Path:
    path = out_dir / "duplicate_candidates.csv"
    fields = [
        "duplicate_key",
        "count",
        "rel_path",
        "size_bytes",
        "authority",
        "artifact_group",
        "doc_type",
    ]
    write_csv(path, duplicate_rows(rows, use_hash), fields)
    return path


def is_kice_source_candidate(row: InventoryRow) -> bool:
    if row.authority != "평가원":
        return False
    if row.extension != ".pdf":
        return False
    if row.artifact_group in {"크롤링산출물", "텍스트추출물", "문서산출물", "EBS교재", "통합본"}:
        return False
    return True


def doc_group(row: InventoryRow) -> str:
    if row.doc_type == "문제":
        return "문제"
    if row.doc_type in {"정답", "해설", "정답해설"}:
        return "정답해설"
    return "미분류"


def kice_matrix_rows(
    rows: list[InventoryRow],
    start_year: int,
    end_year: int,
) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], list[InventoryRow]] = defaultdict(list)
    for row in rows:
        if not is_kice_source_candidate(row):
            continue
        group = doc_group(row)
        if row.academic_year and row.exam_round in KICE_SESSIONS and group in KICE_DOC_GROUPS:
            by_key[(row.academic_year, row.exam_round, group)].append(row)

    output: list[dict[str, object]] = []
    for year in range(start_year, end_year + 1):
        year_text = str(year)
        for session in KICE_SESSIONS:
            problem_items = by_key.get((year_text, session, "문제"), [])
            answer_items = by_key.get((year_text, session, "정답해설"), [])
            if problem_items and answer_items:
                status = "완비"
            elif problem_items:
                status = "정답해설 후보 없음"
            elif answer_items:
                status = "문제 후보 없음"
            else:
                status = "둘 다 없음"

            output.append(
                {
                    "academic_year": year_text,
                    "session": session,
                    "status": status,
                    "problem_count": len(problem_items),
                    "answer_solution_count": len(answer_items),
                    "problem_files": " | ".join(item.rel_path for item in problem_items),
                    "answer_solution_files": " | ".join(item.rel_path for item in answer_items),
                }
            )
    return output


def write_kice_matrix(
    out_dir: Path,
    rows: list[InventoryRow],
    start_year: int,
    end_year: int,
) -> Path:
    path = out_dir / "kice_matrix.csv"
    fields = [
        "academic_year",
        "session",
        "status",
        "problem_count",
        "answer_solution_count",
        "problem_files",
        "answer_solution_files",
    ]
    write_csv(path, kice_matrix_rows(rows, start_year, end_year), fields)
    return path


def summarize(rows: list[InventoryRow]) -> dict[str, object]:
    def counts_for(attr: str) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            counts[getattr(row, attr) or ""] += 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    return {
        "total_files": len(rows),
        "by_extension": counts_for("extension"),
        "by_authority": counts_for("authority"),
        "by_artifact_group": counts_for("artifact_group"),
        "by_doc_type": counts_for("doc_type"),
    }


def write_summary(out_dir: Path, rows: list[InventoryRow]) -> Path:
    path = out_dir / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summarize(rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="생활과 윤리 시험자료 폴더를 스캔하고 관리용 보고서를 생성합니다."
    )
    parser.add_argument("--root", default=DEFAULT_ROOT, help="스캔할 원본 폴더")
    parser.add_argument("--out", default="reports", help="보고서를 저장할 폴더")
    parser.add_argument("--hash", action="store_true", help="파일 내용 해시로 중복을 더 정확히 찾기")
    parser.add_argument("--kice-start", type=int, default=2014, help="평가원 누락 점검 시작 학년도")
    parser.add_argument("--kice-end", type=int, default=2026, help="평가원 누락 점검 종료 학년도")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    out_dir = Path(args.out)

    if not root.exists():
        raise SystemExit(f"원본 폴더를 찾을 수 없습니다: {root}")

    rows = scan_files(root, include_hash=args.hash)
    summary_path = write_summary(out_dir, rows)
    inventory_path = write_inventory(out_dir, rows)
    duplicate_path = write_duplicates(out_dir, rows, use_hash=args.hash)
    matrix_path = write_kice_matrix(out_dir, rows, args.kice_start, args.kice_end)

    print(f"총 {len(rows)}개 파일을 스캔했습니다.")
    print(f"요약: {summary_path}")
    print(f"인벤토리: {inventory_path}")
    print(f"중복 후보: {duplicate_path}")
    print(f"평가원 누락 매트릭스: {matrix_path}")


if __name__ == "__main__":
    main()
