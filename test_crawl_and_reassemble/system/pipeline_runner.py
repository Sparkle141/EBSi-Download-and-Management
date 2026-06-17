from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO


SYSTEM_DIR = Path(__file__).resolve().parent
ROOT_DIR = SYSTEM_DIR.parent
PACKAGE_DIR = SYSTEM_DIR / "packages"

if PACKAGE_DIR.exists():
    sys.path.insert(0, str(PACKAGE_DIR))
if str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

from filename_meta import parse_exam_metadata, safe_path_part
import pdf_to_markdown


DEFAULT_CONFIG: dict[str, Any] = {
    "input_dir": "input",
    "input_dirs": [],
    "intermediate_dir": "intermediate",
    "output_dir": "output",
    "external_output_dir": "",
    "pattern": "*.pdf",
    "recursive": True,
    "line_tolerance": 3.0,
    "include_placeholders": True,
    "blank_before_question": True,
    "make_html": True,
    "make_docx": True,
    "docx_layout": "questions",
    "asset_text": "tables_only",
    "install_packages": True,
    "copy_to_output": True,
    "copy_to_external_output": True,
    "open_output": False,
    "ebsi_reports_mode": "auto",
    "include_legacy_downloads": False,
    "make_llm_bundle": True,
}

REQUIRED_PACKAGES = {
    "pdfplumber": "pdfplumber>=0.11.0",
    "docx": "python-docx>=1.1.0",
    "PIL": "Pillow>=10.0.0",
}


@dataclass(frozen=True)
class InputJob:
    problem_path: Path
    source_bundle: dict[str, Any] | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PDF extraction and exam reassembly as one pipeline.")
    parser.add_argument("--config", type=Path, default=ROOT_DIR / "pipeline_config.json")
    parser.add_argument("--input", "--input-dir", dest="inputs", action="append", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--external-output-dir", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--no-html", action="store_true")
    parser.add_argument("--no-docx", action="store_true")
    parser.add_argument("--no-install-packages", action="store_true")
    parser.add_argument("--open-output", action="store_true")
    args = parser.parse_args(argv)

    config_path = _resolve_path(args.config, ROOT_DIR)
    config = _load_or_create_config(config_path)
    config = _apply_cli_overrides(config, args)

    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"pipeline_run_{datetime.now():%Y%m%d_%H%M%S}.log"

    with log_path.open("w", encoding="utf-8") as log:
        try:
            _log(log, "Integrated exam pipeline started.")
            _log(log, f"Root: {ROOT_DIR}")
            _log(log, f"Config: {config_path}")

            if bool(config.get("install_packages", True)):
                _ensure_packages(config, log)
            else:
                _require_packages(config)
            _reload_pdf_tools()

            jobs = _discover_inputs(config, log)
            if args.limit is not None:
                jobs = jobs[: args.limit]
            if not jobs:
                raise FileNotFoundError("처리할 PDF 파일을 찾지 못했습니다.")

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_manifest: dict[str, Any] = {
                "schema": "exam-reassembler-run-v1",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "root_dir": str(ROOT_DIR),
                "config_path": str(config_path),
                "pdf_count": len(jobs),
                "results": [],
            }

            output_dirs: list[Path] = []
            failed = 0
            for index, job in enumerate(jobs, 1):
                pdf_path = job.problem_path
                _log(log, f"[{index}/{len(jobs)}] Processing: {pdf_path}")
                try:
                    result = _process_pdf(job, config, run_id, log, max_pages=args.max_pages)
                    run_manifest["results"].append(result)
                    output_dir = result.get("output_dir")
                    if output_dir:
                        output_dirs.append(Path(output_dir))
                except Exception as exc:
                    failed += 1
                    _log(log, f"FAILED: {pdf_path}: {exc}")
                    _log(log, traceback.format_exc())
                    run_manifest["results"].append(
                        {
                            "input_pdf": str(pdf_path),
                            "success": False,
                            "error": str(exc),
                            "source_bundle": job.source_bundle,
                        }
                    )

            output_root = _resolve_path(Path(str(config.get("output_dir") or "output")), ROOT_DIR)
            output_root.mkdir(parents=True, exist_ok=True)
            run_manifest_path = output_root / f"run_manifest_{run_id}.json"
            run_manifest_path.write_text(
                json.dumps(run_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if bool(config.get("open_output", False)):
                _open_folder(output_dirs[-1] if output_dirs else output_root, log)

            if failed:
                message = f"일부 실패: 성공 {len(jobs) - failed}개, 실패 {failed}개\n로그: {log_path}"
                _write_status(False, message)
                return 1

            message = f"완료: {len(jobs)}개 PDF 처리\noutput: {output_root}\n로그: {log_path}"
            _write_status(True, message)
            _log(log, "Integrated exam pipeline finished.")
            return 0
        except Exception as exc:
            _log(log, f"ERROR: {exc}")
            _log(log, traceback.format_exc())
            _write_status(False, f"실패: {exc}\n로그: {log_path}")
            return 1


def _apply_cli_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    merged = dict(config)
    if args.inputs:
        merged["input_dir"] = ""
        merged["input_dirs"] = [str(path) for path in args.inputs]
    if args.output_dir:
        merged["output_dir"] = str(args.output_dir)
    if args.external_output_dir:
        merged["external_output_dir"] = str(args.external_output_dir)
    if args.no_html:
        merged["make_html"] = False
    if args.no_docx:
        merged["make_docx"] = False
    if args.no_install_packages:
        merged["install_packages"] = False
    if args.open_output:
        merged["open_output"] = True
    return merged


def _load_or_create_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return dict(DEFAULT_CONFIG)

    with config_path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"설정 파일 형식이 올바르지 않습니다: {config_path}")

    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def _discover_inputs(config: dict[str, Any], log: TextIO) -> list[InputJob]:
    roots: list[Path] = []
    input_dir = _resolve_optional_path(config.get("input_dir"), ROOT_DIR)
    if input_dir:
        roots.append(input_dir)

    for raw in _as_list(config.get("input_dirs")):
        path = _resolve_optional_path(raw, ROOT_DIR)
        if path:
            roots.append(path)

    if not roots:
        roots.append(ROOT_DIR / "input")

    ebsi_jobs, ebsi_report_roots = _discover_ebsi_jobs(roots, config, log)

    pattern = str(config.get("pattern") or "*.pdf")
    recursive = bool(config.get("recursive", True))
    seen: set[str] = set()
    jobs: list[InputJob] = []

    for job in ebsi_jobs:
        key = str(job.problem_path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(job)

    for root in roots:
        if not root.exists():
            _log(log, f"Input path does not exist, skipped: {root}")
            continue
        if str(root.resolve()).lower() in ebsi_report_roots:
            _log(log, f"EBSi reports found near input; generic PDF scan skipped for: {root}")
            continue
        if root.is_file():
            candidates = [root] if root.suffix.lower() == ".pdf" else []
        else:
            candidates = sorted(root.rglob(pattern) if recursive else root.glob(pattern))
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() != ".pdf":
                continue
            key = str(candidate.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            jobs.append(InputJob(problem_path=candidate.resolve()))

    _log(log, f"Discovered PDF jobs: {len(jobs)}")
    return jobs


def _discover_ebsi_jobs(
    roots: list[Path],
    config: dict[str, Any],
    log: TextIO,
) -> tuple[list[InputJob], set[str]]:
    if str(config.get("ebsi_reports_mode") or "auto").lower() == "off":
        return [], set()

    jobs: list[InputJob] = []
    roots_with_reports: set[str] = set()
    all_report_files: set[str] = set()

    for root in roots:
        reports = _find_ebsi_report_files(root)
        if not reports:
            continue
        roots_with_reports.add(str(root.resolve()).lower())
        all_report_files.update(str(report.resolve()).lower() for report in reports)

        records: list[dict[str, Any]] = []
        for report_file in reports:
            try:
                with report_file.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        record = _ebsi_record_from_row(row, report_file, config)
                        if record:
                            records.append(record)
            except Exception as exc:
                _log(log, f"EBSi report skipped: {report_file}: {exc}")

        eligible_keys = _eligible_ebsi_group_keys(root, records)
        if not eligible_keys:
            continue

        grouped: dict[tuple[Any, ...], dict[str, list[dict[str, Any]]]] = {}
        for record in records:
            group_key = _ebsi_group_tuple(record)
            if group_key not in eligible_keys:
                continue
            grouped.setdefault(group_key, {}).setdefault(record["role"], []).append(record)

        for docs in grouped.values():
            problem = _choose_ebsi_record(docs.get("problem") or [], require_pdf=True)
            if not problem:
                continue
            bundle = _make_ebsi_source_bundle(docs, problem)
            jobs.append(InputJob(problem_path=Path(problem["local_path"]).resolve(), source_bundle=bundle))

    _log(log, f"EBSi report files: {len(all_report_files)}")
    _log(log, f"EBSi grouped problem jobs: {len(jobs)}")
    return jobs, roots_with_reports


def _eligible_ebsi_group_keys(root: Path, records: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    if not records:
        return set()

    root_resolved = root.resolve()
    eligible: set[tuple[Any, ...]] = set()
    problem_records = [record for record in records if record.get("role") == "problem"]

    if root.is_file():
        selected = str(root_resolved).lower()
        for record in problem_records:
            if str(Path(record["local_path"]).resolve()).lower() == selected:
                eligible.add(_ebsi_group_tuple(record))
        return eligible

    if not root.exists():
        return set()

    for record in problem_records:
        if _path_is_within(Path(record["local_path"]), root_resolved):
            eligible.add(_ebsi_group_tuple(record))
    return eligible


def _ebsi_group_tuple(record: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(record["group_key"][key] for key in (
        "exam_family",
        "subject",
        "academic_year",
        "execution_year",
        "session",
    ))


def _find_ebsi_report_files(root: Path) -> list[Path]:
    start = root.parent if root.is_file() else root
    candidates: list[Path] = []
    for base in [start, *list(start.parents)[:6]]:
        reports_dir = base / "reports"
        if not reports_dir.is_dir():
            continue
        for pattern in (
            "selected_download_sources_*.csv",
            "official_sources_*.csv",
            "official_exam_sources*.csv",
            "availability_*.csv",
        ):
            candidates.extend(sorted(reports_dir.glob(pattern)))

    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path.resolve())
    return result


def _ebsi_record_from_row(
    row: dict[str, str],
    report_file: Path,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    role = _normalize_doc_group(row.get("doc_group"))
    if role not in {"problem", "answer", "solution"}:
        return None

    local_path = _resolve_report_local_path(row.get("local_path"), report_file)
    if not local_path:
        return None
    if not bool(config.get("include_legacy_downloads", False)) and _path_has_part(local_path, "legacy"):
        return None
    if not local_path.exists():
        return None

    exam_family, exam_family_label = _infer_exam_family(row, local_path)
    subject_profile = _subject_profile_from_path(local_path)
    subject = _clean_text(row.get("subject")) or _subject_from_profile(subject_profile) or ""
    academic_year = _first_int(row.get("academic_year"))
    execution_year = _first_int(row.get("execution_year")) or academic_year
    session = _clean_text(row.get("session")) or _session_from_path(local_path) or ""

    return {
        "role": role,
        "report_path": str(report_file),
        "local_path": str(local_path.resolve()),
        "url": _clean_text(row.get("url")),
        "sha256": _clean_text(row.get("sha256")),
        "title": _clean_text(row.get("title")),
        "recommended_filename": _clean_text(row.get("recommended_filename")) or local_path.name,
        "source_org": _clean_text(row.get("source_org")),
        "source_route": _clean_text(row.get("source_route")),
        "content_type": _clean_text(row.get("content_type")),
        "content_length": _first_int(row.get("content_length")),
        "note": _clean_text(row.get("note")),
        "group_key": {
            "exam_family": exam_family,
            "subject": subject,
            "academic_year": academic_year,
            "execution_year": execution_year,
            "session": session,
        },
        "exam_family": exam_family,
        "exam_family_label": exam_family_label,
        "subject": subject,
        "subject_profile": subject_profile,
        "academic_year": academic_year,
        "execution_year": execution_year,
        "execution_month": _format_month(row.get("execution_month"), session),
        "session": session,
    }


def _make_ebsi_source_bundle(
    docs: dict[str, list[dict[str, Any]]],
    problem: dict[str, Any],
) -> dict[str, Any]:
    answer = _choose_ebsi_record(docs.get("answer") or [], require_pdf=False)
    solution = _choose_ebsi_record(docs.get("solution") or [], require_pdf=True)
    if answer:
        answer_status = "source_available"
        answer_role = "answer_image"
    elif solution:
        answer_status = "source_available"
        answer_role = "solution_pdf"
    else:
        answer_status = "missing"
        answer_role = "missing"

    bundle = {
        "provider": "EBSi",
        "exam_family": problem.get("exam_family"),
        "exam_family_label": problem.get("exam_family_label"),
        "subject": problem.get("subject"),
        "subject_profile": problem.get("subject_profile"),
        "academic_year": problem.get("academic_year"),
        "execution_year": problem.get("execution_year"),
        "execution_month": problem.get("execution_month"),
        "session": problem.get("session"),
        "source_title": problem.get("title"),
        "source_route": problem.get("source_route"),
        "problem_path": problem.get("local_path"),
        "problem_url": problem.get("url"),
        "problem_sha256": problem.get("sha256"),
        "answer_path": answer.get("local_path") if answer else None,
        "answer_url": answer.get("url") if answer else None,
        "answer_sha256": answer.get("sha256") if answer else None,
        "solution_path": solution.get("local_path") if solution else None,
        "solution_url": solution.get("url") if solution else None,
        "solution_sha256": solution.get("sha256") if solution else None,
        "answer_extraction_status": answer_status,
        "answer_key": None,
        "answer_source_role": answer_role,
        "source_documents": {
            "problem": _strip_internal_ebsi_fields(problem),
            "answer": _strip_internal_ebsi_fields(answer) if answer else None,
            "solution": _strip_internal_ebsi_fields(solution) if solution else None,
        },
    }
    return bundle


def _choose_ebsi_record(records: list[dict[str, Any]], require_pdf: bool) -> dict[str, Any] | None:
    if not records:
        return None
    candidates = records
    if require_pdf:
        pdfs = [record for record in records if Path(record["local_path"]).suffix.lower() == ".pdf"]
        if pdfs:
            candidates = pdfs
    existing = [record for record in candidates if Path(record["local_path"]).exists()]
    return existing[0] if existing else candidates[0]


def _strip_internal_ebsi_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"group_key"}}


def _resolve_report_local_path(raw_value: str | None, report_file: Path) -> Path | None:
    text = _clean_text(raw_value)
    if not text:
        return None
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if path.is_absolute():
        return path
    report_root = report_file.parent.parent
    return (report_root / path).resolve()


def _normalize_doc_group(value: str | None) -> str | None:
    text = _clean_text(value).lower()
    compact = text.replace(" ", "")
    if not compact:
        return None
    if "문제" in compact or "problem" in compact:
        return "problem"
    if "정답" in compact or "answer" in compact:
        return "answer"
    if "해설" in compact or "solution" in compact or "explanation" in compact:
        return "solution"
    return None


def _infer_exam_family(row: dict[str, str], local_path: Path) -> tuple[str, str]:
    haystack = " ".join(
        [
            _clean_text(row.get("exam_family")),
            _clean_text(row.get("source_org")),
            _clean_text(row.get("source_route")),
            _clean_text(row.get("title")),
            _subject_profile_from_path(local_path),
            str(local_path),
        ]
    ).lower()
    if "office" in haystack or "교육청" in haystack or "학력평가" in haystack:
        return "office", "교육청"
    return "kice", "평가원"


def _subject_profile_from_path(path: Path) -> str:
    parts = list(path.parts)
    lowered = [part.lower() for part in parts]
    for marker in ("current", "legacy"):
        if marker in lowered:
            index = lowered.index(marker)
            if index > 0:
                return parts[index - 1]
    return ""


def _subject_from_profile(profile: str) -> str:
    return profile.removeprefix("교육청 ").strip()


def _session_from_path(path: Path) -> str:
    for part in path.parts:
        if re.fullmatch(r"\d{1,2}월|수능", part):
            return part
    return ""


def _format_month(value: str | None, session: str) -> str:
    month = _first_int(value) or _first_int(session)
    return f"{month:02d}" if month else ""


def _first_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _path_has_part(path: Path, name: str) -> bool:
    return any(part.lower() == name.lower() for part in path.parts)


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _process_pdf(
    job: InputJob,
    config: dict[str, Any],
    run_id: str,
    log: TextIO,
    max_pages: int | None = None,
) -> dict[str, Any]:
    pdf_path = job.problem_path
    intermediate_root = _resolve_path(Path(str(config.get("intermediate_dir") or "intermediate")), ROOT_DIR)
    output_root = _resolve_path(Path(str(config.get("output_dir") or "output")), ROOT_DIR)
    intermediate_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    stem = safe_path_part(pdf_path.stem)
    result_dir = _unique_dir(intermediate_root / f"{stem}_{run_id}")
    result_dir.mkdir(parents=True, exist_ok=False)

    asset_dir = result_dir / "assets"
    markdown, layouts, assets, line_records = pdf_to_markdown.transcribe_pdf(
        pdf_path,
        line_tolerance=float(config.get("line_tolerance") or 3.0),
        include_placeholders=bool(config.get("include_placeholders", True)),
        blank_before_question=bool(config.get("blank_before_question", True)),
        asset_output_dir=asset_dir,
        max_pages=max_pages,
    )

    md_path = result_dir / f"{stem}.md"
    layout_path = result_dir / f"{stem}.layout.json"
    assets_path = result_dir / f"{stem}.assets.json"
    lines_path = result_dir / f"{stem}.lines.json"
    metadata_path = result_dir / "metadata.json"

    md_path.write_text(markdown, encoding="utf-8")
    pdf_to_markdown.write_debug_json(layout_path, layouts)
    pdf_to_markdown.write_assets_json(assets_path, assets, base_dir=result_dir)
    pdf_to_markdown.write_text_lines_json(lines_path, line_records)

    exam_meta = parse_exam_metadata(pdf_path)
    asset_counts = Counter(asset.kind for asset in assets)
    metadata = {
        "schema": "exam-reassembler-result-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_pdf": str(pdf_path),
        "intermediate_dir": str(result_dir),
        "markdown": str(md_path),
        "layout": str(layout_path),
        "assets": str(assets_path),
        "lines": str(lines_path),
        "exam": exam_meta.to_dict(),
        "pages": [asdict(layout) for layout in layouts],
        "asset_count": len(assets),
        "asset_counts_by_kind": dict(asset_counts),
        "scan_fallback_count": asset_counts.get("page_screenshot", 0),
        "line_count": len(line_records),
        "pipeline": {
            "make_html": bool(config.get("make_html", True)),
            "make_docx": bool(config.get("make_docx", True)),
            "docx_layout": str(config.get("docx_layout") or "questions"),
            "asset_text": str(config.get("asset_text") or "tables_only"),
            "make_llm_bundle": bool(config.get("make_llm_bundle", True)),
        },
    }
    if job.source_bundle:
        metadata.update(job.source_bundle)
        metadata["source_bundle"] = job.source_bundle
    llm_bundle_path = None
    if bool(config.get("make_llm_bundle", True)):
        llm_bundle_path = _write_llm_bundle(result_dir, stem, md_path, metadata)
        if llm_bundle_path:
            metadata["llm_bundle_markdown"] = str(llm_bundle_path)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    generated = _run_assemblers(result_dir, config, log)
    metadata["final_outputs"] = [str(path) for path in generated]

    llm_json, llm_md = _write_llm_manifest(
        result_dir=result_dir,
        stem=stem,
        metadata=metadata,
        generated=generated,
    )
    metadata["llm_manifest_json"] = str(llm_json)
    metadata["llm_manifest_markdown"] = str(llm_md)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    output_dir = result_dir
    if bool(config.get("copy_to_output", True)):
        output_dir = _copy_result_to_output(result_dir, output_root, log)

    external_output_dir = ""
    if bool(config.get("copy_to_external_output", True)):
        external_root = _resolve_optional_path(config.get("external_output_dir"), ROOT_DIR)
        if external_root:
            external_output = _copy_result_to_output(output_dir, external_root, log)
            external_output_dir = str(external_output)

    return {
        "input_pdf": str(pdf_path),
        "success": True,
        "intermediate_dir": str(result_dir),
        "output_dir": str(output_dir),
        "external_output_dir": external_output_dir,
        "metadata": str(metadata_path),
        "llm_manifest_json": str(llm_json),
        "llm_manifest_markdown": str(llm_md),
        "llm_bundle_markdown": str(llm_bundle_path) if llm_bundle_path else "",
        "final_outputs": [str(path) for path in generated],
        "source_bundle": job.source_bundle,
    }


def _run_assemblers(result_dir: Path, config: dict[str, Any], log: TextIO) -> list[Path]:
    generated: list[Path] = []
    if bool(config.get("make_html", True)):
        from assembler_html import assemble_html

        html_path = assemble_html(result_dir)
        generated.append(html_path)
        _log(log, f"HTML generated: {html_path}")

    if bool(config.get("make_docx", True)):
        from assembler_docx import assemble_docx

        docx_path = assemble_docx(
            result_dir,
            layout_mode=str(config.get("docx_layout") or "questions"),
            asset_text_mode=str(config.get("asset_text") or "tables_only"),
        )
        generated.append(docx_path)
        _log(log, f"DOCX generated: {docx_path}")

    return generated


def _write_llm_bundle(
    result_dir: Path,
    stem: str,
    md_path: Path,
    metadata: dict[str, Any],
) -> Path | None:
    source_bundle = metadata.get("source_bundle")
    if not isinstance(source_bundle, dict):
        return None
    if not source_bundle.get("answer_path") and not source_bundle.get("solution_path"):
        return None

    problem_markdown = md_path.read_text(encoding="utf-8-sig")
    bundle_path = result_dir / f"{stem}.llm_bundle.md"
    lines = [
        "# LLM 합본: 문제 + 공식 정답/해설",
        "",
        "> 이 파일은 문제 전사 원본 뒤에 EBSi 보고서 메타데이터로 연결된 공식 정답/해설 부록을 붙인 LLM 인계용 파일입니다.",
        "> 순수 문제 전사 원본은 같은 폴더의 원래 `.md` 파일에 보존됩니다.",
        "",
        "## 문제 전사",
        "",
        problem_markdown.rstrip(),
        "",
        "---",
        "",
        "## 공식 정답/해설 부록",
        "",
        "### 연결 기준",
        "",
        f"- provider: {source_bundle.get('provider') or ''}",
        f"- exam_family: {source_bundle.get('exam_family') or ''}",
        f"- exam_family_label: {source_bundle.get('exam_family_label') or ''}",
        f"- subject: {source_bundle.get('subject') or ''}",
        f"- subject_profile: {source_bundle.get('subject_profile') or ''}",
        f"- academic_year: {source_bundle.get('academic_year') or ''}",
        f"- execution_year: {source_bundle.get('execution_year') or ''}",
        f"- execution_month: {source_bundle.get('execution_month') or ''}",
        f"- session: {source_bundle.get('session') or ''}",
        "",
        "### 정답",
        "",
    ]
    _append_source_lines(
        lines,
        path=source_bundle.get("answer_path"),
        url=source_bundle.get("answer_url"),
        sha256=source_bundle.get("answer_sha256"),
        missing_note="EBSi 보고서에서 연결된 정답 이미지가 없습니다.",
    )
    lines.extend(
        [
            "",
            "### 해설",
            "",
        ]
    )
    _append_source_lines(
        lines,
        path=source_bundle.get("solution_path"),
        url=source_bundle.get("solution_url"),
        sha256=source_bundle.get("solution_sha256"),
        missing_note="EBSi 보고서에서 연결된 해설 PDF가 없습니다.",
    )
    lines.extend(
        [
            "",
            "### 처리 메모",
            "",
            f"- answer_extraction_status: {source_bundle.get('answer_extraction_status') or ''}",
            f"- answer_source_role: {source_bundle.get('answer_source_role') or ''}",
            "- 정답 이미지와 해설 PDF의 본문은 이 파일 안에 강제로 전사하지 않습니다. LLM에 넘길 때 위 파일을 함께 첨부하거나 경로를 참조시키는 방식으로 사용합니다.",
            "- 이 부록은 EBSi 보고서의 group_key 기준으로 연결된 경우에만 생성됩니다.",
            "",
            "### 공식 출처 메타데이터 JSON",
            "",
            "```json",
            json.dumps(source_bundle, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    bundle_path.write_text("\n".join(lines), encoding="utf-8")
    return bundle_path


def _append_source_lines(
    lines: list[str],
    *,
    path: Any,
    url: Any,
    sha256: Any,
    missing_note: str,
) -> None:
    if not path:
        lines.append(f"- 상태: {missing_note}")
        return
    lines.append(f"- 파일: `{path}`")
    if url:
        lines.append(f"- 원본 URL: {url}")
    if sha256:
        lines.append(f"- sha256: `{sha256}`")


def _write_llm_manifest(
    result_dir: Path,
    stem: str,
    metadata: dict[str, Any],
    generated: list[Path],
) -> tuple[Path, Path]:
    assets_path = result_dir / f"{stem}.assets.json"
    lines_path = result_dir / f"{stem}.lines.json"
    layout_path = result_dir / f"{stem}.layout.json"
    md_path = result_dir / f"{stem}.md"

    assets_data = _read_json_list(assets_path)
    page_rows = [
        {
            "page_no": page.get("page_no"),
            "is_two_column": page.get("is_two_column"),
            "page_width": page.get("page_width"),
            "page_height": page.get("page_height"),
            "difficult_page": page.get("difficult_page"),
            "fallback_reason": page.get("fallback_reason"),
        }
        for page in metadata.get("pages", [])
        if isinstance(page, dict)
    ]

    manifest = {
        "schema": "llm-exam-reassembly-manifest-v1",
        "purpose": "PDF 시험지를 텍스트, 표, 그림, 위치 메타데이터와 최종 조립물로 넘기기 위한 색인입니다.",
        "source_pdf": metadata.get("input_pdf"),
        "exam": metadata.get("exam"),
        "source_bundle": metadata.get("source_bundle"),
        "primary_text_file": md_path.name,
        "llm_bundle_file": Path(str(metadata.get("llm_bundle_markdown"))).name
        if metadata.get("llm_bundle_markdown")
        else None,
        "metadata_files": {
            "layout": layout_path.name,
            "assets": assets_path.name,
            "lines": lines_path.name,
            "metadata": "metadata.json",
        },
        "final_output_files": [path.name for path in generated],
        "asset_summary": metadata.get("asset_counts_by_kind", {}),
        "page_count": len(page_rows),
        "line_count": metadata.get("line_count"),
        "asset_index": [
            {
                "label": item.get("label"),
                "kind": item.get("kind"),
                "page_no": item.get("page_no"),
                "bbox": item.get("bbox"),
                "file": item.get("file"),
                "width": item.get("width"),
                "height": item.get("height"),
            }
            for item in assets_data
            if isinstance(item, dict)
        ],
        "page_index": page_rows,
    }

    json_path = result_dir / "llm_manifest.json"
    md_manifest_path = result_dir / "llm_manifest.md"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    md_manifest_path.write_text(_render_llm_manifest_markdown(manifest), encoding="utf-8")
    return json_path, md_manifest_path


def _render_llm_manifest_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# LLM 전달용 시험지 색인",
        "",
        f"- 원본 PDF: {manifest.get('source_pdf')}",
        f"- 본문 텍스트: {manifest.get('primary_text_file')}",
        f"- 문제+정답/해설 LLM 합본: {manifest.get('llm_bundle_file') or ''}",
        f"- 페이지 수: {manifest.get('page_count')}",
        f"- 텍스트 라인 수: {manifest.get('line_count')}",
        f"- 최종 산물: {', '.join(manifest.get('final_output_files') or [])}",
        "",
    ]
    source_bundle = manifest.get("source_bundle")
    if isinstance(source_bundle, dict):
        lines.extend(
            [
                "## EBSi 공식 출처",
                "",
                f"- provider: {source_bundle.get('provider')}",
                f"- exam_family: {source_bundle.get('exam_family')}",
                f"- subject: {source_bundle.get('subject')}",
                f"- academic_year: {source_bundle.get('academic_year')}",
                f"- execution_year: {source_bundle.get('execution_year')}",
                f"- session: {source_bundle.get('session')}",
                f"- problem_path: {source_bundle.get('problem_path')}",
                f"- answer_path: {source_bundle.get('answer_path')}",
                f"- solution_path: {source_bundle.get('solution_path')}",
                f"- answer_source_role: {source_bundle.get('answer_source_role')}",
                "",
            ]
        )
    lines.extend(["## 메타데이터 파일", ""])
    for label, file_name in (manifest.get("metadata_files") or {}).items():
        lines.append(f"- {label}: {file_name}")
    lines.extend(["", "## 에셋 색인", "", "| label | kind | page | file | bbox |", "|---|---|---:|---|---|"])
    for asset in manifest.get("asset_index") or []:
        bbox = json.dumps(asset.get("bbox"), ensure_ascii=False)
        lines.append(
            f"| {asset.get('label') or ''} | {asset.get('kind') or ''} | "
            f"{asset.get('page_no') or ''} | {asset.get('file') or ''} | {bbox} |"
        )
    lines.append("")
    return "\n".join(lines)


def _read_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        value = data.get("assets") or data.get("items") or []
        return value if isinstance(value, list) else []
    return []


def _copy_result_to_output(result_dir: Path, output_root: Path, log: TextIO) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    destination = _unique_dir(output_root / result_dir.name)
    shutil.copytree(result_dir, destination)
    _log(log, f"Copied result folder: {destination}")
    return destination


def _ensure_packages(config: dict[str, Any], log: TextIO) -> None:
    missing = _missing_packages(config)
    if not missing:
        _log(log, "Required packages are already available.")
        return

    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pip", "install", "--target", str(PACKAGE_DIR)]
    command.extend(missing)
    _log(log, f"Installing packages into system/packages: {', '.join(missing)}")
    result = subprocess.run(command, stdout=log, stderr=log, text=True)
    if result.returncode != 0:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], stdout=log, stderr=log, text=True)
        result = subprocess.run(command, stdout=log, stderr=log, text=True)
    if result.returncode != 0:
        raise RuntimeError("필수 패키지 설치에 실패했습니다. logs 폴더의 실행 로그를 확인해 주세요.")

    if str(PACKAGE_DIR) not in sys.path:
        sys.path.insert(0, str(PACKAGE_DIR))
    importlib.invalidate_caches()
    _require_packages(config)


def _reload_pdf_tools() -> None:
    global pdf_to_markdown
    importlib.invalidate_caches()
    pdf_to_markdown = importlib.reload(pdf_to_markdown)


def _require_packages(config: dict[str, Any]) -> None:
    missing = _missing_packages(config)
    if missing:
        raise RuntimeError(f"필수 패키지가 없습니다: {', '.join(missing)}")


def _missing_packages(config: dict[str, Any]) -> list[str]:
    imports = ["pdfplumber"]
    if bool(config.get("make_docx", True)):
        imports.extend(["docx", "PIL"])

    missing: list[str] = []
    for import_name in imports:
        if importlib.util.find_spec(import_name) is None:
            missing.append(REQUIRED_PACKAGES[import_name])
    return missing


def _unique_dir(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}_{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"중복 폴더가 너무 많습니다: {path}")


def _resolve_optional_path(value: Any, base: Path) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _resolve_path(Path(os.path.expandvars(os.path.expanduser(text))), base)


def _resolve_path(path: Path, base: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _open_folder(path: Path, log: TextIO) -> None:
    _log(log, f"Opening folder: {path}")
    if os.name == "nt":
        os.startfile(str(path))
        return
    subprocess.Popen(["xdg-open", str(path)])


def _write_status(success: bool, message: str) -> None:
    status_path = ROOT_DIR / "logs" / "last_run_status.txt"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status = "SUCCESS" if success else "FAILED"
    status_path.write_text(f"{status}\n{message}\n", encoding="utf-8")


def _log(log: TextIO, message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", file=log, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
