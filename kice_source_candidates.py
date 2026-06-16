from __future__ import annotations

import argparse
import csv
import urllib.error
import urllib.request
from pathlib import Path


SUBJECT_CODE = "42_1"
SUBJECT_NAME = "생활과 윤리"


def read_matrix(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def slug_for(academic_year: str, session: str) -> str:
    yy = academic_year[-2:]
    if session == "수능":
        return f"suneung-{yy}"
    if session == "6월":
        return f"{yy}suneung-06mo"
    if session == "9월":
        return f"{yy}suneung-09mo"
    raise ValueError(f"지원하지 않는 평가원 시행 구분입니다: {session}")


def url_for(academic_year: str, session: str, doc_group: str) -> str:
    slug = slug_for(academic_year, session)
    if doc_group == "index":
        return f"https://cdn.kice.re.kr/{slug}/index.html"
    if doc_group == "문제":
        return f"https://cdn.kice.re.kr/{slug}/{slug}_{SUBJECT_CODE}.pdf"
    if doc_group == "정답":
        return f"https://cdn.kice.re.kr/{slug}/{slug}_{SUBJECT_CODE}a.pdf"
    raise ValueError(f"지원하지 않는 문서 구분입니다: {doc_group}")


def probe_url(url: str, timeout: int) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf,text/html,*/*",
            "Range": "bytes=0-2047",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(64)
            return {
                "reachable": "yes",
                "http_status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "content_length": response.headers.get("content-length", ""),
                "probe_error": "",
            }
    except urllib.error.HTTPError as exc:
        return {
            "reachable": "no",
            "http_status": exc.code,
            "content_type": exc.headers.get("content-type", "") if exc.headers else "",
            "content_length": exc.headers.get("content-length", "") if exc.headers else "",
            "probe_error": str(exc),
        }
    except Exception as exc:
        return {
            "reachable": "unknown",
            "http_status": "",
            "content_type": "",
            "content_length": "",
            "probe_error": f"{type(exc).__name__}: {exc}",
        }


def missing_doc_groups(row: dict[str, str]) -> list[str]:
    groups: list[str] = []
    if int(row["problem_count"]) == 0:
        groups.append("문제")
    if int(row["answer_solution_count"]) == 0:
        groups.append("정답")
    return groups


def build_rows(matrix_rows: list[dict[str, str]], probe: bool, timeout: int) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for matrix_row in matrix_rows:
        if matrix_row["status"] == "완비":
            continue

        academic_year = matrix_row["academic_year"]
        session = matrix_row["session"]
        index_url = url_for(academic_year, session, "index")

        for doc_group in missing_doc_groups(matrix_row):
            candidate_url = url_for(academic_year, session, doc_group)
            probe_result = probe_url(candidate_url, timeout) if probe else {
                "reachable": "not_checked",
                "http_status": "",
                "content_type": "",
                "content_length": "",
                "probe_error": "",
            }
            yy = academic_year[-2:]
            session_label = "대학수학능력시험" if session == "수능" else f"{session} 모의평가"
            filename = f"{academic_year}학년도-{session_label}-{SUBJECT_NAME}-{doc_group}.pdf"

            output.append(
                {
                    "academic_year": academic_year,
                    "session": session,
                    "target_doc_group": doc_group,
                    "subject": SUBJECT_NAME,
                    "source_kind": "official_kice_cdn_pattern",
                    "candidate_url": candidate_url,
                    "index_url": index_url,
                    "download_filename": filename,
                    "local_status": matrix_row["status"],
                    "problem_count": matrix_row["problem_count"],
                    "answer_solution_count": matrix_row["answer_solution_count"],
                    "reachable": probe_result["reachable"],
                    "http_status": probe_result["http_status"],
                    "content_type": probe_result["content_type"],
                    "content_length": probe_result["content_length"],
                    "probe_error": probe_result["probe_error"],
                    "note": f"{yy}학년도 평가원 {session} {doc_group} 후보 URL입니다. 접근 가능하면 임시 폴더에 먼저 내려받아 해시 비교하세요.",
                }
            )
    return output


def write_missing_targets(path: Path, matrix_rows: list[dict[str, str]]) -> None:
    rows: list[dict[str, object]] = []
    for row in matrix_rows:
        if row["status"] == "완비":
            continue
        for doc_group in missing_doc_groups(row):
            rows.append(
                {
                    "academic_year": row["academic_year"],
                    "session": row["session"],
                    "missing_doc_group": doc_group,
                    "local_status": row["status"],
                    "problem_count": row["problem_count"],
                    "answer_solution_count": row["answer_solution_count"],
                    "problem_files": row["problem_files"],
                    "answer_solution_files": row["answer_solution_files"],
                }
            )
    write_csv(
        path,
        rows,
        [
            "academic_year",
            "session",
            "missing_doc_group",
            "local_status",
            "problem_count",
            "answer_solution_count",
            "problem_files",
            "answer_solution_files",
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="평가원 누락 매트릭스에서 공식 CDN 다운로드 후보 URL을 생성합니다."
    )
    parser.add_argument("--matrix", default="reports/kice_matrix.csv", help="평가원 누락 매트릭스 CSV")
    parser.add_argument("--out", default="reports/kice_download_candidates.csv", help="후보 URL 보고서")
    parser.add_argument("--missing-out", default="reports/kice_missing_targets.csv", help="누락 대상 요약 CSV")
    parser.add_argument("--no-probe", action="store_true", help="후보 URL 접근성 점검을 건너뜁니다")
    parser.add_argument("--timeout", type=int, default=12, help="URL 하나당 접근성 점검 제한 시간")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_rows = read_matrix(Path(args.matrix))
    write_missing_targets(Path(args.missing_out), matrix_rows)
    rows = build_rows(matrix_rows, probe=not args.no_probe, timeout=args.timeout)
    write_csv(
        Path(args.out),
        rows,
        [
            "academic_year",
            "session",
            "target_doc_group",
            "subject",
            "source_kind",
            "candidate_url",
            "index_url",
            "download_filename",
            "local_status",
            "problem_count",
            "answer_solution_count",
            "reachable",
            "http_status",
            "content_type",
            "content_length",
            "probe_error",
            "note",
        ],
    )
    reachable = sum(1 for row in rows if row["reachable"] == "yes")
    print(f"누락 대상 {len(rows)}개 후보를 생성했습니다.")
    print(f"접근 가능 후보: {reachable}개")
    print(f"후보 보고서: {args.out}")
    print(f"누락 대상 요약: {args.missing_out}")


if __name__ == "__main__":
    main()
