from __future__ import annotations

import argparse
import csv
from pathlib import Path


DOC_PROBLEM = "문제"
DOC_ANSWER = "정답"
DOC_SOLUTION = "해설"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields = list(rows[0])
    else:
        fields = [
            "academic_year",
            "session",
            "current_status",
            "missing_problem",
            "missing_answer_solution",
            "official_problem_path",
            "official_answer_path",
            "official_solution_path",
            "ready_to_copy_paths",
            "recommended_action",
            "note",
        ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def official_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, dict[str, str]]]:
    lookup: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    for row in rows:
        key = (row["academic_year"], row["session"])
        lookup.setdefault(key, {})[row["doc_group"]] = row
    return lookup


def local_path(row: dict[str, str] | None) -> str:
    if not row or row.get("reachable") != "yes":
        return ""
    return row.get("local_path", "")


def build_gap_plan(
    matrix_rows: list[dict[str, str]],
    official_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    official = official_lookup(official_rows)
    plan_rows: list[dict[str, str]] = []

    for matrix in matrix_rows:
        key = (matrix["academic_year"], matrix["session"])
        current_has_problem = as_int(matrix.get("problem_count", "")) > 0
        current_has_answer_solution = as_int(matrix.get("answer_solution_count", "")) > 0

        missing_problem = not current_has_problem
        missing_answer_solution = not current_has_answer_solution
        if not (missing_problem or missing_answer_solution):
            continue

        official_for_key = official.get(key, {})
        problem_path = local_path(official_for_key.get(DOC_PROBLEM))
        answer_path = local_path(official_for_key.get(DOC_ANSWER))
        solution_path = local_path(official_for_key.get(DOC_SOLUTION))

        ready_paths: list[str] = []
        actions: list[str] = []
        notes: list[str] = []

        if missing_problem:
            if problem_path:
                ready_paths.append(problem_path)
                actions.append("공식 문제 PDF로 보완 가능")
            else:
                actions.append("문제 PDF 공식 파일 추가 탐색 필요")

        if missing_answer_solution:
            if solution_path:
                ready_paths.append(solution_path)
                actions.append("공식 해설 PDF로 보완 가능")
            elif answer_path:
                ready_paths.append(answer_path)
                actions.append("공식 정답 이미지로 부분 보완 가능")
            else:
                actions.append("정답/해설 공식 파일 추가 탐색 필요")

            if answer_path:
                ready_paths.append(answer_path)
            elif solution_path:
                notes.append("별도 정답 이미지는 없지만 해설 PDF가 있음")

        plan_rows.append(
            {
                "academic_year": matrix["academic_year"],
                "session": matrix["session"],
                "current_status": matrix.get("status", ""),
                "missing_problem": "yes" if missing_problem else "no",
                "missing_answer_solution": "yes" if missing_answer_solution else "no",
                "official_problem_path": problem_path,
                "official_answer_path": answer_path,
                "official_solution_path": solution_path,
                "ready_to_copy_paths": "; ".join(dict.fromkeys(path for path in ready_paths if path)),
                "recommended_action": "; ".join(actions),
                "note": "; ".join(notes),
            }
        )

    return plan_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="현재 보유 상태와 공식 다운로드 파일을 대조해 보강 계획표를 만듭니다.")
    parser.add_argument("--matrix", default="reports/kice_matrix.csv", help="현재 보유 상태 매트릭스 CSV")
    parser.add_argument(
        "--official",
        default="reports/official_exam_sources_2014_2026_verified.csv",
        help="공식 출처 및 다운로드 결과 CSV",
    )
    parser.add_argument("--out", default="reports/official_gap_plan_2014_2026.csv", help="보강 계획표 CSV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    matrix_rows = read_csv(Path(args.matrix))
    official_rows = read_csv(Path(args.official))
    plan_rows = build_gap_plan(matrix_rows, official_rows)
    write_csv(Path(args.out), plan_rows)
    ready = sum(1 for row in plan_rows if row["ready_to_copy_paths"])
    print(f"보강 대상 {len(plan_rows)}개를 정리했습니다.")
    print(f"공식 파일로 바로 보완 가능한 대상: {ready}개")
    print(f"보강 계획표: {args.out}")


if __name__ == "__main__":
    main()
