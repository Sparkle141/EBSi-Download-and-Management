from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


CONFIG_PATH = Path("archive_config.json")


@dataclass
class ArchiveConfig:
    profile_name: str
    source_root: Path
    copy_root: Path
    reports_dir: Path
    download_dir: Path
    legacy_download_dir: Path
    academic_year_start: int
    academic_year_end: int
    sessions: list[str]
    future_check_default: bool
    future_years_ahead: int
    official_sources_report: Path
    official_download_manifest: Path
    latest_gap_report: Path
    latest_apply_manifest: Path


def load_config(path: Path = CONFIG_PATH) -> ArchiveConfig:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return ArchiveConfig(
        profile_name=data["profile_name"],
        source_root=Path(data["source_root"]),
        copy_root=Path(data["copy_root"]),
        reports_dir=Path(data["reports_dir"]),
        download_dir=Path(data["download_dir"]),
        legacy_download_dir=Path(data["legacy_download_dir"]),
        academic_year_start=int(data["academic_year_start"]),
        academic_year_end=int(data["academic_year_end"]),
        sessions=list(data["sessions"]),
        future_check_default=bool(data.get("future_check_default", False)),
        future_years_ahead=int(data.get("future_years_ahead", 1)),
        official_sources_report=Path(data["official_sources_report"]),
        official_download_manifest=Path(data["official_download_manifest"]),
        latest_gap_report=Path(data["latest_gap_report"]),
        latest_apply_manifest=Path(data["latest_apply_manifest"]),
    )


def save_config(config: ArchiveConfig, path: Path = CONFIG_PATH) -> None:
    data = {
        "profile_name": config.profile_name,
        "source_root": config.source_root.as_posix(),
        "copy_root": config.copy_root.as_posix(),
        "reports_dir": config.reports_dir.as_posix(),
        "download_dir": config.download_dir.as_posix(),
        "legacy_download_dir": config.legacy_download_dir.as_posix(),
        "academic_year_start": config.academic_year_start,
        "academic_year_end": config.academic_year_end,
        "sessions": config.sessions,
        "future_check_default": config.future_check_default,
        "future_years_ahead": config.future_years_ahead,
        "official_sources_report": config.official_sources_report.as_posix(),
        "official_download_manifest": config.official_download_manifest.as_posix(),
        "latest_gap_report": config.latest_gap_report.as_posix(),
        "latest_apply_manifest": config.latest_apply_manifest.as_posix(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def future_academic_year(today: date | None = None, years_ahead: int = 1) -> int:
    today = today or date.today()
    return today.year + years_ahead


def current_execution_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year


def academic_years(config: ArchiveConfig, include_future: bool = False) -> list[str]:
    end = config.academic_year_end
    if include_future:
        end = max(end, future_academic_year(years_ahead=config.future_years_ahead))
    return [str(year) for year in range(config.academic_year_start, end + 1)]


def academic_year_end(config: ArchiveConfig, include_future: bool = False) -> int:
    years = academic_years(config, include_future=include_future)
    return int(years[-1])
