from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from archive_config import academic_years, load_config


EBSI_PAGE = "https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd=D300"
EBSI_AJAX = "https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperListAjax.ajax"


def ok_result(name: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "status": "ok", "detail": detail}


def fail_result(name: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": "fail", "detail": detail}


def warn_result(name: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": "warn", "detail": detail}


def check_path(name: str, path: Path, must_exist: bool = True) -> dict[str, str]:
    if path.exists():
        return ok_result(name, str(path))
    if must_exist:
        return fail_result(name, f"not found: {path}")
    parent = path.parent
    if parent.exists():
        return warn_result(name, f"will be created under: {parent}")
    return fail_result(name, f"parent not found: {parent}")


def check_dns(host: str, timeout: int) -> dict[str, str]:
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        addresses = socket.getaddrinfo(host, 443)
        unique = sorted({item[4][0] for item in addresses})
        return ok_result(f"DNS {host}", ", ".join(unique[:3]))
    except Exception as exc:
        return fail_result(f"DNS {host}", f"{type(exc).__name__}: {exc}")
    finally:
        socket.setdefaulttimeout(old_timeout)


def fetch_url(name: str, url: str, timeout: int, data: bytes | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": EBSI_PAGE,
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        headers["X-Requested-With"] = "XMLHttpRequest"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        start = time.perf_counter()
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(256)
            elapsed_ms = round((time.perf_counter() - start) * 1000)
            content_type = response.headers.get("content-type", "")
            return ok_result(name, f"HTTP {response.status}, {elapsed_ms} ms, {content_type}")
    except Exception as exc:
        return fail_result(name, f"{type(exc).__name__}: {exc}")


def check_ebsi_ajax(timeout: int) -> dict[str, str]:
    payload = urllib.parse.urlencode(
        {
            "targetCd": "D300",
            "yearList": "2025",
            "monthList": "06",
            "arOrd": "5",
            "subjIdList": "63002",
            "sort": "recent",
            "paperId": "",
            "paperNo": "",
            "lvl": "",
        }
    ).encode("utf-8")
    return fetch_url("EBSi 기출 AJAX", EBSI_AJAX, timeout=timeout, data=payload)


def run_checks(include_future: bool, timeout: int) -> dict[str, object]:
    config = load_config()
    checks: list[dict[str, str]] = []
    checks.append(ok_result("Python", sys.version.split()[0]))
    checks.append(check_path("원본 저장 폴더", config.source_root))
    checks.append(check_path("저장 경로(복사 목적지)", config.copy_root, must_exist=False))
    checks.append(check_path("보고서 폴더", config.reports_dir, must_exist=False))
    checks.append(check_path("다운로드 원본 폴더", config.download_dir, must_exist=False))
    checks.append(check_path("legacy 이관 폴더", config.legacy_download_dir, must_exist=False))
    checks.append(check_dns("www.ebsi.co.kr", timeout))
    checks.append(check_dns("wdown.ebsi.co.kr", timeout))
    checks.append(fetch_url("EBSi 기출문제 페이지", EBSI_PAGE, timeout=timeout))
    checks.append(check_ebsi_ajax(timeout))

    return {
        "profile": config.profile_name,
        "academic_years": academic_years(config, include_future=include_future),
        "include_future": include_future,
        "checks": checks,
    }


def write_reports(payload: dict[str, object], reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "environment_check.json"
    text_path = reports_dir / "environment_check.txt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"Profile: {payload['profile']}",
        f"Academic years: {', '.join(payload['academic_years'])}",
        f"Include future: {payload['include_future']}",
        "",
    ]
    for item in payload["checks"]:
        lines.append(f"[{item['status'].upper()}] {item['name']} - {item['detail']}")
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, text_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="환경 점검 보고서를 생성합니다.")
    parser.add_argument("--include-future", action="store_true", help="다음 학년도까지 점검 범위에 포함합니다.")
    parser.add_argument("--timeout", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    payload = run_checks(include_future=args.include_future, timeout=args.timeout)
    json_path, text_path = write_reports(payload, config.reports_dir)
    failed = [item for item in payload["checks"] if item["status"] == "fail"]
    warned = [item for item in payload["checks"] if item["status"] == "warn"]
    print(f"환경 점검 완료: 실패 {len(failed)}개, 주의 {len(warned)}개")
    print(f"JSON: {json_path}")
    print(f"TXT: {text_path}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
