from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


EBSI_PREVIOUS_PAPER_PAGE = "https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd=D300"
EBSI_PREVIOUS_PAPER_AJAX = "https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperListAjax.ajax"
EBSI_DOWNLOAD_BASE = "https://wdown.ebsi.co.kr/W61001/01exam"

SUBJECT_ID = "63002"
SUBJECT_NAME = "생활과 윤리"
AREA_ORD = "5"
TARGET_CD = "D300"

SESSION_TO_MONTH = {
    "3월": "03",
    "4월": "04",
    "5월": "05",
    "6월": "06",
    "7월": "07",
    "9월": "09",
    "10월": "10",
    "수능": "11",
}

SPECIAL_EXECUTION_MONTHS = {
    ("2021", "수능"): "12",
    ("2023", "9월"): "08",
}

SESSION_LABEL = {
    "3월": "3월-학력평가",
    "4월": "4월-학력평가",
    "5월": "5월-학력평가",
    "6월": "6월-모의평가",
    "7월": "7월-학력평가",
    "9월": "9월-모의평가",
    "10월": "10월-학력평가",
    "수능": "대학수학능력시험",
}

EBS_DOCS = {
    "문제": {
        "function": "goDownLoadP",
        "kind": "problem_pdf",
        "extension": ".pdf",
        "source_org": "EBSi",
    },
    "정답": {
        "function": "goDownLoadJ",
        "kind": "answer_image",
        "extension": ".png",
        "source_org": "EBSi",
    },
    "해설": {
        "function": "goDownLoadH",
        "kind": "solution_pdf",
        "extension": ".pdf",
        "source_org": "EBSi",
    },
}


@dataclass
class SourceRow:
    academic_year: str
    execution_year: str
    session: str
    execution_month: str
    subject: str
    doc_group: str
    source_org: str
    source_route: str
    title: str
    url: str
    recommended_filename: str
    reachable: str
    http_status: str
    content_type: str
    content_length: str
    sha256: str
    local_path: str
    note: str


def academic_to_execution_year(academic_year: str) -> str:
    return str(int(academic_year) - 1)


def display_to_execution_year(display_year: str, exam_family: str) -> str:
    if exam_family == "office":
        return str(int(display_year))
    return academic_to_execution_year(display_year)


def academic_year_from_execution(execution_year: str, month: str) -> str:
    if month in {"11", "12"}:
        return str(int(execution_year) + 1)
    return str(int(execution_year) + 1)


def execution_month_for(academic_year: str, session: str) -> str:
    return SPECIAL_EXECUTION_MONTHS.get((academic_year, session), SESSION_TO_MONTH[session])


RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


def request_bytes(url: str, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 20) -> bytes:
    merged_headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": EBSI_PREVIOUS_PAPER_PAGE,
    }
    if headers:
        merged_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=merged_headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE_HTTP_STATUS and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError("request retry loop exhausted")


def fetch_ebsi_listing(
    execution_year: str,
    month: str,
    timeout: int,
    subject_id: str = SUBJECT_ID,
    area_ord: str = AREA_ORD,
    target_cd: str = TARGET_CD,
) -> str:
    payload = urllib.parse.urlencode(
        {
            "targetCd": target_cd,
            "yearList": execution_year,
            "monthList": month,
            "arOrd": area_ord,
            "subjIdList": subject_id,
            "sort": "recent",
            "paperId": "",
            "paperNo": "",
            "lvl": "",
        }
    ).encode("utf-8")
    data = request_bytes(
        EBSI_PREVIOUS_PAPER_AJAX,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=timeout,
    )
    return data.decode("utf-8", "replace")


def first_arg_for_function(listing_html: str, function_name: str) -> str:
    pattern = re.compile(rf"{re.escape(function_name)}\('([^']*)'", re.S)
    match = pattern.search(listing_html)
    return html.unescape(match.group(1)) if match else ""


def title_from_listing(listing_html: str) -> str:
    match = re.search(r'<div class="qus_tit">(.*?)</div>', listing_html, re.S)
    if not match:
        return ""
    title = re.sub(r"<.*?>", "", match.group(1))
    title = html.unescape(title)
    return re.sub(r"\s+", " ", title.replace("\xa0", " ")).strip()


def absolute_ebs_url(raw: str) -> str:
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return EBSI_DOWNLOAD_BASE + raw


def recommended_filename(
    academic_year: str,
    session: str,
    subject_name: str,
    doc_group: str,
    extension: str,
    exam_family: str = "kice",
) -> str:
    if exam_family == "office":
        return f"{academic_year}년-{SESSION_LABEL[session]}-{subject_name}-{doc_group}{extension}"
    return f"{academic_year}학년도-{SESSION_LABEL[session]}-{subject_name}-{doc_group}{extension}"


def filename_extension(default_extension: str, url: str, content_type: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".pdf", ".png", ".jpg", ".jpeg"}:
        return suffix

    content_type = content_type.split(";", 1)[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }.get(content_type, default_extension)


def probe_url(url: str, timeout: int) -> dict[str, str]:
    if not url:
        return {
            "reachable": "no",
            "http_status": "",
            "content_type": "",
            "content_length": "",
            "note": "URL 없음",
        }
    try:
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": EBSI_PREVIOUS_PAPER_PAGE,
                        "Range": "bytes=0-63",
                    },
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    response.read(1)
                    return {
                        "reachable": "yes",
                        "http_status": str(response.status),
                        "content_type": response.headers.get("content-type", ""),
                        "content_length": response.headers.get("content-length", ""),
                        "note": "",
                    }
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE_HTTP_STATUS and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            except urllib.error.URLError:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
    except urllib.error.HTTPError as exc:
        return {
            "reachable": "no",
            "http_status": str(exc.code),
            "content_type": exc.headers.get("content-type", "") if exc.headers else "",
            "content_length": exc.headers.get("content-length", "") if exc.headers else "",
            "note": str(exc),
        }
    except Exception as exc:
        return {
            "reachable": "unknown",
            "http_status": "",
            "content_type": "",
            "content_length": "",
            "note": f"{type(exc).__name__}: {exc}",
        }


def build_ebsi_rows(
    academic_years: Iterable[str],
    sessions: Iterable[str],
    timeout: int,
    subject_id: str = SUBJECT_ID,
    subject_name: str = SUBJECT_NAME,
    area_ord: str = AREA_ORD,
    target_cd: str = TARGET_CD,
    exam_family: str = "kice",
) -> list[SourceRow]:
    rows: list[SourceRow] = []
    seen_requests: set[tuple[str, str]] = set()

    for academic_year in academic_years:
        execution_year = display_to_execution_year(academic_year, exam_family)
        for session in sessions:
            month = execution_month_for(academic_year, session)
            key = (execution_year, month)
            if key in seen_requests:
                continue
            seen_requests.add(key)

            try:
                listing = fetch_ebsi_listing(
                    execution_year,
                    month,
                    timeout,
                    subject_id=subject_id,
                    area_ord=area_ord,
                    target_cd=target_cd,
                )
                title = title_from_listing(listing)
                fetch_note = ""
            except Exception as exc:
                listing = ""
                title = ""
                fetch_note = f"EBSi 목록 조회 실패: {type(exc).__name__}: {exc}"

            for doc_group, config in EBS_DOCS.items():
                raw_url = first_arg_for_function(listing, config["function"])
                url = absolute_ebs_url(raw_url) if raw_url else ""
                probe = probe_url(url, timeout) if url else {
                    "reachable": "no",
                    "http_status": "",
                    "content_type": "",
                    "content_length": "",
                    "note": "EBSi 목록에서 해당 버튼 URL을 찾지 못함",
                }
                extension = filename_extension(config["extension"], url, probe["content_type"])
                rows.append(
                    SourceRow(
                        academic_year=academic_year,
                        execution_year=execution_year,
                        session=session,
                        execution_month=month,
                        subject=subject_name,
                        doc_group=doc_group,
                        source_org=config["source_org"],
                        source_route=EBSI_PREVIOUS_PAPER_PAGE,
                        title=title,
                        url=url,
                        recommended_filename=recommended_filename(
                            academic_year,
                            session,
                            subject_name,
                            doc_group,
                            extension,
                            exam_family,
                        ),
                        reachable=probe["reachable"],
                        http_status=probe["http_status"],
                        content_type=probe["content_type"],
                        content_length=probe["content_length"],
                        sha256="",
                        local_path="",
                        note=fetch_note or probe["note"],
                    )
                )
    return rows


def write_sources(path: Path, rows: list[SourceRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(SourceRow.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def filter_rows(rows: list[SourceRow], only_keys: Iterable[str]) -> list[SourceRow]:
    keys = {key.strip() for key in only_keys if key.strip()}
    if not keys:
        return rows
    selected: list[SourceRow] = []
    for row in rows:
        candidates = {
            f"{row.academic_year}|{row.session}|{row.doc_group}",
            f"{row.academic_year}/{row.session}/{row.doc_group}",
            f"{row.academic_year}:{row.session}:{row.doc_group}",
        }
        if candidates & keys:
            selected.append(row)
    return selected


def file_signature_ok(path: Path, doc_group: str) -> bool:
    head = path.read_bytes()[:8]
    if doc_group in {"문제", "해설"}:
        return head.startswith(b"%PDF")
    if doc_group == "정답":
        return head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def year_folder_name(row: SourceRow) -> str:
    if row.recommended_filename.startswith(f"{row.academic_year}년-"):
        return f"{row.academic_year}년"
    return f"{row.academic_year}학년도"


def download_rows(
    rows: list[SourceRow],
    out_dir: Path,
    timeout: int,
    legacy_dir: Path | None = None,
    archive_existing: str = "changed",
) -> dict[str, object]:
    downloaded: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []
    archived: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    legacy_dir = legacy_dir or (out_dir.parent / "legacy")

    for row in rows:
        if row.reachable != "yes" or not row.url:
            skipped.append({"url": row.url, "reason": "접근 가능 후보가 아님"})
            continue

        session_dir = out_dir / year_folder_name(row) / row.session
        session_dir.mkdir(parents=True, exist_ok=True)
        target = session_dir / row.recommended_filename
        temp_target = target.with_name(target.name + ".download")

        try:
            data = request_bytes(row.url, timeout=timeout)
            temp_target.write_bytes(data)
            if not file_signature_ok(temp_target, row.doc_group):
                raise ValueError("파일 서명이 예상 형식과 다름")

            new_sha256 = sha256_file(temp_target)
            if target.exists():
                old_sha256 = sha256_file(target)
                if old_sha256 == new_sha256 and archive_existing != "always":
                    temp_target.unlink()
                    row.sha256 = old_sha256
                    row.local_path = target.as_posix()
                    unchanged.append({"url": row.url, "path": target.as_posix(), "sha256": old_sha256})
                    continue

                if archive_existing in {"changed", "always"}:
                    legacy_target = legacy_dir / run_id / target.relative_to(out_dir)
                    legacy_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(legacy_target))
                    archived.append(
                        {
                            "url": row.url,
                            "from": target.as_posix(),
                            "to": legacy_target.as_posix(),
                            "sha256": old_sha256,
                        }
                    )
                else:
                    target.unlink()

            temp_target.replace(target)
            row.sha256 = new_sha256
            row.local_path = target.as_posix()
            downloaded.append({"url": row.url, "path": target.as_posix(), "sha256": row.sha256})
        except Exception as exc:
            if temp_target.exists():
                temp_target.unlink()
            failed.append({"url": row.url, "reason": f"{type(exc).__name__}: {exc}"})

    return {
        "downloaded": downloaded,
        "unchanged": unchanged,
        "archived": archived,
        "skipped": skipped,
        "failed": failed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EBSi 공식 기출문제 목록에서 생활과 윤리 개별 시험 문제/정답/해설 출처를 수집합니다."
    )
    parser.add_argument("--academic-years", nargs="+", default=["2026"], help="학년도 목록")
    parser.add_argument("--sessions", nargs="+", default=["6월", "9월", "수능"], choices=list(SESSION_TO_MONTH), help="시행 구분")
    parser.add_argument("--subject-id", default=SUBJECT_ID, help="EBSi 과목 ID")
    parser.add_argument("--subject-name", default=SUBJECT_NAME, help="표시 과목명")
    parser.add_argument("--area-ord", default=AREA_ORD, help="EBSi 영역 순번")
    parser.add_argument("--target-cd", default=TARGET_CD, help="EBSi 대상 코드")
    parser.add_argument("--exam-family", choices=["kice", "office"], default="kice", help="평가원/교육청 연도 규칙")
    parser.add_argument("--only-keys", nargs="*", default=[], help="선택 다운로드 키: 학년도|회차|문서종류")
    parser.add_argument("--out", default="reports/official_exam_sources.csv", help="공식 출처 보고서 CSV")
    parser.add_argument("--download", action="store_true", help="접근 가능한 공식 파일을 임시 다운로드 폴더에 저장")
    parser.add_argument("--download-dir", default="official_downloads", help="임시 다운로드 폴더")
    parser.add_argument("--legacy-dir", default="", help="기존 다운로드 파일 이관 폴더")
    parser.add_argument(
        "--archive-existing",
        choices=["changed", "always", "never"],
        default="changed",
        help="기존 파일 처리 방식: changed=내용이 바뀔 때만 legacy 이관, always=매번 이관, never=이관 없이 교체",
    )
    parser.add_argument("--manifest", default="reports/official_download_manifest.json", help="다운로드 결과 매니페스트")
    parser.add_argument("--timeout", type=int, default=20, help="요청 제한 시간")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_ebsi_rows(
        args.academic_years,
        args.sessions,
        args.timeout,
        subject_id=args.subject_id,
        subject_name=args.subject_name,
        area_ord=args.area_ord,
        target_cd=args.target_cd,
        exam_family=args.exam_family,
    )
    rows = filter_rows(rows, args.only_keys)

    manifest: dict[str, object] | None = None
    if args.download:
        manifest = download_rows(
            rows,
            Path(args.download_dir),
            args.timeout,
            legacy_dir=Path(args.legacy_dir) if args.legacy_dir else None,
            archive_existing=args.archive_existing,
        )
        manifest_path = Path(args.manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_sources(Path(args.out), rows)

    reachable = sum(1 for row in rows if row.reachable == "yes")
    print(f"공식 출처 후보 {len(rows)}개를 수집했습니다.")
    print(f"접근 가능 후보: {reachable}개")
    print(f"출처 보고서: {args.out}")
    if manifest is not None:
        print(f"다운로드/갱신: {len(manifest['downloaded'])}개")
        print(f"동일 파일 유지: {len(manifest.get('unchanged', []))}개")
        print(f"legacy 이관: {len(manifest.get('archived', []))}개")
        print(f"다운로드 매니페스트: {args.manifest}")


if __name__ == "__main__":
    main()
