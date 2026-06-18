from __future__ import annotations

import json
import os
import csv
import re
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from archive_config import (
    academic_year_end,
    academic_years,
    current_execution_year,
    future_academic_year,
    load_config,
    save_config,
)


APP_DIR = Path(__file__).resolve().parent
FAMILY_ORDER = ["평가원", "교육청"]
DEFAULT_SESSIONS_BY_FAMILY = {
    "평가원": ["6월", "9월", "수능"],
    "교육청": ["3월", "4월", "5월", "7월", "10월"],
}
REASSEMBLY_OUTPUT_SUFFIX = "전사 및 조립"
REASSEMBLY_SKIP_DIR_MARKERS = {REASSEMBLY_OUTPUT_SUFFIX, "legacy"}


def scoped_sessions_for_family(family: str, sessions: list[str] | None = None) -> list[str]:
    allowed = DEFAULT_SESSIONS_BY_FAMILY.get(family)
    if not allowed:
        return list(sessions or [])
    if not sessions:
        return list(allowed)
    if any(session not in allowed for session in sessions):
        return list(allowed)
    selected = [session for session in allowed if session in sessions]
    return selected or list(allowed)


class ArchiveApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("EBSi 시험자료 관리")
        self.root.geometry("1060x780")
        self.root.minsize(980, 720)
        self.config = load_config(APP_DIR / "archive_config.json")
        self.include_future = BooleanVar(value=self.config.future_check_default)
        self.source_root = StringVar(value=str(self.config.source_root))
        self.copy_root = StringVar(value=str(self.config.copy_root))
        self.subjects = self._load_subjects()
        initial_subject = self._subject_by_profile(self.config.profile_name) or self._first_subject()
        self.exam_family_names = self._family_names()
        self.exam_family_name = StringVar(value=self._subject_family(initial_subject))
        self.subject_names = self._subject_names_for_family(self.exam_family_name.get())
        initial_display = self._subject_display(initial_subject)
        self.subject_name = StringVar(
            value=initial_display if initial_display in self.subject_names else self.subject_names[0]
        )
        self.provider_label = StringVar(value="")
        self.download_label = StringVar(value="")
        self.availability_rows: list[dict[str, str]] = []
        self.sort_reverse: dict[str, bool] = {}
        self.status = StringVar(value="준비됨")
        self._build()
        self._refresh_range_label()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text="EBSi 시험자료 관리", font=("맑은 고딕", 16, "bold"))
        title.pack(anchor="w")

        desc = ttk.Label(
            frame,
            text="EBSi 공식 기출문제 파일을 과목별로 확인하고, 선택 다운로드와 저장 경로 복사를 한 화면에서 처리합니다.",
        )
        desc.pack(anchor="w", pady=(4, 12))

        settings = ttk.LabelFrame(frame, text="기본 경로", padding=10)
        settings.pack(fill="x")

        ttk.Label(settings, text="시험 구분").grid(row=0, column=0, sticky="w", pady=3)
        self.family_combo = ttk.Combobox(
            settings,
            textvariable=self.exam_family_name,
            values=self.exam_family_names,
            state="readonly",
        )
        self.family_combo.grid(row=0, column=1, sticky="ew", padx=(8, 4), pady=3)
        self.family_combo.bind("<<ComboboxSelected>>", lambda event: self._on_family_changed())

        ttk.Label(settings, text="과목").grid(row=1, column=0, sticky="w", pady=3)
        self.subject_combo = ttk.Combobox(settings, textvariable=self.subject_name, values=self.subject_names, state="readonly")
        self.subject_combo.grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=3)
        self.subject_combo.bind("<<ComboboxSelected>>", lambda event: self._on_subject_changed())
        ttk.Label(settings, textvariable=self.provider_label).grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=3)

        self._path_row(settings, "관리 대상 폴더", self.source_root, self.choose_source, self.open_source, row=2)
        self._path_row(settings, "저장 경로", self.copy_root, self.choose_copy_root, self.open_copy_root, row=3)
        ttk.Label(settings, text="다운로드 원본").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Label(settings, textvariable=self.download_label).grid(row=4, column=1, columnspan=3, sticky="w", padx=(8, 0), pady=3)

        future_row = ttk.Frame(settings)
        future_row.grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            future_row,
            text="다음 학년도까지 확인",
            variable=self.include_future,
            command=self._refresh_range_label,
        ).pack(side="left")
        self.range_label = ttk.Label(future_row, text="")
        self.range_label.pack(side="left", padx=(12, 0))

        actions = ttk.LabelFrame(frame, text="핵심 흐름", padding=10)
        actions.pack(fill="x", pady=(12, 0))

        buttons = [
            ("EBS 현황 확인", self.check_availability),
            ("선택 다운로드", self.download_selected),
            ("선택 항목 저장", self.copy_selected_to_save_path),
            ("저장 경로 열기", self.open_copy_root),
        ]
        for index, (label, command) in enumerate(buttons):
            button = ttk.Button(actions, text=label, command=command)
            button.grid(row=0, column=index, padx=4, pady=4, sticky="ew")
            actions.columnconfigure(index, weight=1)

        status_bar = ttk.LabelFrame(frame, text="작업 상태", padding=(8, 5))
        status_bar.pack(fill="x", pady=(8, 0))
        ttk.Label(status_bar, textvariable=self.status).pack(side="left", padx=(2, 0))

        available = ttk.LabelFrame(frame, text="EBS 목록", padding=8)
        available.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(
            available,
            text="여러 항목은 Ctrl/Shift로 선택할 수 있고, 표 머리글을 누르면 정렬됩니다.",
        ).pack(anchor="w", pady=(0, 6))
        self.availability_tree = ttk.Treeview(
            available,
            columns=("year", "session", "doc", "state", "title"),
            show="headings",
            selectmode="extended",
            height=8,
        )
        for col, text, width in [
            ("year", "학년도", 80),
            ("session", "회차", 80),
            ("doc", "문서", 80),
            ("state", "상태", 90),
            ("title", "공식 제목", 520),
        ]:
            self.availability_tree.heading(col, text=text, command=lambda c=col: self.sort_availability(c))
            self.availability_tree.column(col, width=width, stretch=(col == "title"))
        self.availability_tree.pack(fill="both", expand=True)
        tree_buttons = ttk.Frame(available)
        tree_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(tree_buttons, text="가능 항목 전체 선택", command=self.select_all_available).pack(side="left")
        ttk.Button(tree_buttons, text="선택 해제", command=self.clear_availability_selection).pack(side="left", padx=(6, 0))

        next_steps = ttk.LabelFrame(frame, text="전사 및 재조립", padding=8)
        next_steps.pack(fill="x", pady=(10, 0))
        next_buttons = [
            ("다운로드 원본 전사/재조립", self.reassemble_downloads),
            ("재조립 결과 열기", self.open_reassembly_output),
            ("재조립 로그 열기", self.open_reassembly_logs),
        ]
        for index, (label, command) in enumerate(next_buttons):
            button = ttk.Button(next_steps, text=label, command=command)
            button.grid(row=0, column=index, padx=4, pady=4, sticky="ew")
            next_steps.columnconfigure(index, weight=1)

        utility_steps = ttk.LabelFrame(frame, text="편의 기능", padding=8)
        utility_steps.pack(fill="x", pady=(10, 0))
        utility_buttons = [
            ("환경 점검", self.env_check),
            ("관리 대상 폴더 확인", self.open_source),
            ("관리 대상 점검", self.scan_status),
            ("공식 다운로드 새로고침", self.refresh_downloads),
            ("누락/재다운로드 보고서", self.make_gap_report),
            ("누락 보고서 기준 반영", self.apply_to_copy_root),
            ("보고서 확인", self.open_reports),
            ("버튼 기능 안내", self.show_button_help),
        ]
        for index, (label, command) in enumerate(utility_buttons):
            button = ttk.Button(utility_steps, text=label, command=command)
            button.grid(row=index // 4, column=index % 4, padx=4, pady=4, sticky="ew")
            utility_steps.columnconfigure(index % 4, weight=1)

        log_frame = ttk.LabelFrame(frame, text="처리 내역", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log = ScrolledText(log_frame, height=9, font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self._refresh_subject_labels()

    def _path_row(self, parent: ttk.LabelFrame, label: str, var: StringVar, choose, open_func, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=(8, 4), pady=3)
        ttk.Button(parent, text="지정", command=choose).grid(row=row, column=2, padx=4, pady=3)
        ttk.Button(parent, text="열기", command=open_func).grid(row=row, column=3, padx=(4, 0), pady=3)
        parent.columnconfigure(1, weight=1)

    def _refresh_range_label(self) -> None:
        end = academic_year_end(self.config, include_future=self.include_future.get())
        kice_year = future_academic_year(years_ahead=self.config.future_years_ahead)
        office_year = current_execution_year()
        self.range_label.configure(
            text=f"점검 범위: {self.config.academic_year_start}-{end}학년도"
            + (
                f"  (올해 시행: 평가원 {kice_year}학년도 / 교육청 {office_year}학년도)"
                if self.include_future.get()
                else ""
            )
        )

    def _load_subjects(self) -> list[dict[str, str]]:
        path = APP_DIR / "subjects.json"
        if not path.exists():
            return [
                {
                    "name": "생활과 윤리",
                    "provider": "EBSi",
                    "exam_family": "평가원",
                    "target_cd": "D300",
                    "area_ord": "5",
                    "subject_id": "63002",
                    "enabled": True,
                }
            ]
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _subject_by_profile(self, profile_name: str) -> dict[str, str] | None:
        for subject in self.subjects:
            if subject["name"] == profile_name:
                return subject
        return None

    def _first_subject(self) -> dict[str, str]:
        for subject in self.subjects:
            if subject.get("enabled", True):
                return subject
        return self.subjects[0]

    def _subject_family(self, subject: dict[str, str]) -> str:
        return subject.get("exam_family") or "평가원"

    def _subject_display(self, subject: dict[str, str]) -> str:
        if subject.get("display_name"):
            return subject["display_name"]
        return subject["name"].removeprefix("교육청 ").strip()

    def _subjects_for_family(self, family: str) -> list[dict[str, str]]:
        return [subject for subject in self.subjects if self._subject_family(subject) == family]

    def _family_names(self) -> list[str]:
        families = [self._subject_family(subject) for subject in self.subjects]
        ordered = [family for family in FAMILY_ORDER if family in families]
        ordered.extend(family for family in families if family not in ordered)
        return ordered

    def _subject_names_for_family(self, family: str) -> list[str]:
        return [self._subject_display(subject) for subject in self._subjects_for_family(family)]

    def _refresh_subject_choices(self) -> None:
        self.subject_names = self._subject_names_for_family(self.exam_family_name.get())
        self.subject_combo.configure(values=self.subject_names)
        if not self.subject_names:
            self.subject_name.set("")
            return
        if self.subject_name.get() not in self.subject_names:
            self.subject_name.set(self.subject_names[0])

    def _selected_subject(self) -> dict[str, str]:
        family = self.exam_family_name.get()
        display_name = self.subject_name.get()
        for subject in self._subjects_for_family(family):
            if self._subject_display(subject) == display_name:
                return subject
        family_subjects = self._subjects_for_family(family)
        return family_subjects[0] if family_subjects else self._first_subject()

    def _official_subject_name(self) -> str:
        subject = self._selected_subject()
        if subject.get("official_subject_name"):
            return subject["official_subject_name"]
        return subject["name"].removeprefix("교육청 ").strip()

    def _safe_subject_name(self) -> str:
        subject = self._selected_subject()
        return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", subject["name"]).strip("_")

    def _subject_download_dir(self) -> Path:
        return Path("downloads") / self._selected_subject()["name"] / "current"

    def _subject_legacy_dir(self) -> Path:
        return Path("downloads") / self._selected_subject()["name"] / "legacy"

    def _subject_sources_report(self, suffix: str = "availability") -> Path:
        safe = self._safe_subject_name()
        end = academic_year_end(self.config, include_future=self.include_future.get())
        return self.config.reports_dir / f"{suffix}_{safe}_{self.config.academic_year_start}_{end}.csv"

    def _subject_manifest(self, suffix: str = "download") -> Path:
        safe = self._safe_subject_name()
        end = academic_year_end(self.config, include_future=self.include_future.get())
        return self.config.reports_dir / f"{suffix}_{safe}_{self.config.academic_year_start}_{end}.json"

    def _reassembly_root(self) -> Path:
        return APP_DIR / "test_crawl_and_reassemble"

    def _reassembly_output_dir(self) -> Path:
        return APP_DIR / self._subject_download_dir()

    def _default_sessions_for_subject(self, subject: dict[str, str]) -> list[str]:
        family = self._subject_family(subject)
        return scoped_sessions_for_family(family, self.config.sessions)

    def _subject_sessions(self, subject: dict[str, str]) -> list[str]:
        family = self._subject_family(subject)
        return scoped_sessions_for_family(family, list(subject.get("sessions") or []))

    def _on_family_changed(self) -> None:
        self._refresh_subject_choices()
        self._on_subject_changed()

    def _on_subject_changed(self) -> None:
        subject = self._selected_subject()
        self.config.profile_name = subject["name"]
        self.config.sessions = self._subject_sessions(subject) or self._default_sessions_for_subject(subject)
        self.config.download_dir = self._subject_download_dir()
        self.config.legacy_download_dir = self._subject_legacy_dir()
        self.config.official_sources_report = self._subject_sources_report("official_sources")
        self.config.official_download_manifest = self._subject_manifest("official_download_manifest")
        if subject.get("source_root"):
            self.source_root.set(subject["source_root"])
            self.config.source_root = Path(subject["source_root"])
        else:
            default_source = self._subject_download_dir()
            self.source_root.set(str(default_source))
            self.config.source_root = default_source
        if subject.get("copy_root"):
            self.copy_root.set(subject["copy_root"])
            self.config.copy_root = Path(subject["copy_root"])
        else:
            default_copy = Path("exports") / subject["name"]
            self.copy_root.set(str(default_copy))
            self.config.copy_root = default_copy
        self.save_paths()
        self._refresh_subject_labels()
        self._clear_availability()
        self.log_line(f"선택: {self.exam_family_name.get()} / {self.subject_name.get()}")
        if not subject.get("enabled", True):
            messagebox.showinfo("확장 예정", subject.get("note", "아직 지원하지 않는 과목입니다."))

    def _refresh_subject_labels(self) -> None:
        subject = self._selected_subject()
        provider = subject.get("provider", "")
        family = subject.get("exam_family", "")
        subject_id = subject.get("subject_id", "")
        parts = [part for part in [provider, family] if part]
        parts.append(f"과목 ID {subject_id}" if subject_id else "과목 ID 미확인")
        if subject.get("experimental"):
            parts.append("experimental")
        if not subject.get("enabled", True):
            parts.append("준비 중")
        self.provider_label.set(" / ".join(parts))
        self.download_label.set(str(APP_DIR / self._subject_download_dir()))

    def _ensure_official_ready(self) -> bool:
        subject = self._selected_subject()
        if not subject.get("enabled", True):
            messagebox.showinfo("확장 예정", subject.get("note", "아직 지원하지 않는 과목입니다."))
            return False
        missing = [name for name in ("subject_id", "area_ord", "target_cd") if not subject.get(name)]
        if missing:
            messagebox.showinfo(
                "공식 루트 미확인",
                f"{self.exam_family_name.get()} / {self.subject_name.get()}의 공식 다운로드 정보가 아직 비어 있습니다.",
            )
            return False
        return True

    def log_line(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    def save_paths(self) -> None:
        self.config.source_root = Path(self.source_root.get())
        self.config.copy_root = Path(self.copy_root.get())
        save_config(self.config, APP_DIR / "archive_config.json")

    def choose_source(self) -> None:
        path = filedialog.askdirectory(title="관리 대상 폴더 선택", initialdir=self._dialog_initial_dir(self.source_root.get()))
        if path:
            self.source_root.set(path)
            self.save_paths()

    def choose_copy_root(self) -> None:
        path = filedialog.askdirectory(title="저장 경로 선택", initialdir=self._dialog_initial_dir(self.copy_root.get()))
        if path:
            self.copy_root.set(path)
            self.save_paths()

    def _dialog_initial_dir(self, raw_path: str) -> str:
        path = Path(raw_path)
        if path.exists():
            return str(path)
        parent = path.parent
        if parent.exists():
            return str(parent)
        return str(APP_DIR)

    def open_path(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            if messagebox.askyesno("폴더 없음", f"폴더가 아직 없습니다.\n만들고 열까요?\n\n{target}"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                return
        os.startfile(target)

    def _ensure_download_folders(self) -> None:
        (APP_DIR / self._subject_download_dir()).mkdir(parents=True, exist_ok=True)
        (APP_DIR / self._subject_legacy_dir()).mkdir(parents=True, exist_ok=True)

    def _ensure_copy_root(self) -> None:
        target = Path(self.copy_root.get())
        if not target.is_absolute():
            target = APP_DIR / target
        target.mkdir(parents=True, exist_ok=True)

    def open_source(self) -> None:
        self.open_path(self.source_root.get())

    def open_copy_root(self) -> None:
        self.open_path(self.copy_root.get())

    def open_reports(self) -> None:
        self.open_path(str(APP_DIR / self.config.reports_dir))

    def open_reassembly_output(self) -> None:
        self.open_path(str(self._reassembly_output_dir()))

    def open_reassembly_logs(self) -> None:
        self.open_path(str(self._reassembly_root() / "logs"))

    def reassemble_downloads(self) -> None:
        input_dir = APP_DIR / self._subject_download_dir()
        targets = self._discover_reassembly_targets(input_dir)
        if not targets:
            messagebox.showinfo(
                "전사할 PDF 없음",
                "먼저 EBS 현황 확인 후 문제/해설 PDF를 다운로드해 주세요.\n영어 듣기 음성은 보관만 하고 전사하지 않습니다.",
            )
            return
        selected_targets = self._choose_reassembly_targets(targets)
        if not selected_targets:
            return
        command = [
            sys.executable,
            "reassemble_downloads_by_folder.py",
        ]
        for target in selected_targets:
            command.extend(["--input-dir", str(target)])
        command.extend(["--manifest", str(self._subject_manifest("reassembly_manifest"))])
        self.run_async("다운로드 원본 전사/재조립", command, allow_fail=True)

    def _should_skip_reassembly_path(self, path: Path) -> bool:
        return any(marker in part for part in path.parts for marker in REASSEMBLY_SKIP_DIR_MARKERS)

    def _discover_reassembly_targets(self, input_dir: Path) -> list[dict[str, object]]:
        if not input_dir.exists():
            return []

        folders: set[Path] = set()
        for pdf in input_dir.rglob("*.pdf"):
            try:
                relative = pdf.relative_to(input_dir)
            except ValueError:
                relative = pdf
            if self._should_skip_reassembly_path(relative):
                continue
            folders.add(pdf.parent)

        targets: list[dict[str, object]] = []
        for folder in sorted(folders, key=lambda item: item.as_posix()):
            pdfs = sorted(pdf for pdf in folder.glob("*.pdf") if pdf.is_file())
            try:
                label = str(folder.relative_to(input_dir))
            except ValueError:
                label = str(folder)
            targets.append({"folder": folder, "label": label, "pdf_count": len(pdfs)})
        return targets

    def _choose_reassembly_targets(self, targets: list[dict[str, object]]) -> list[Path]:
        dialog = Toplevel(self.root)
        dialog.title("전사/재조립 대상 선택")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("680x420")
        dialog.minsize(560, 320)

        container = ttk.Frame(dialog, padding=12)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="전사/재조립할 다운로드 결과물을 선택하세요. 여러 항목은 Ctrl/Shift로 선택할 수 있습니다.").pack(
            anchor="w", pady=(0, 8)
        )

        tree = ttk.Treeview(
            container,
            columns=("folder", "pdfs"),
            show="headings",
            selectmode="extended",
            height=12,
        )
        tree.heading("folder", text="다운로드 결과물")
        tree.heading("pdfs", text="PDF")
        tree.column("folder", width=520, stretch=True)
        tree.column("pdfs", width=70, anchor="center", stretch=False)
        tree.pack(fill="both", expand=True)

        for index, target in enumerate(targets):
            tree.insert("", "end", iid=str(index), values=(target["label"], target["pdf_count"]))
        tree.selection_set([str(index) for index in range(len(targets))])

        selected: list[Path] = []

        def select_all() -> None:
            tree.selection_set([str(index) for index in range(len(targets))])

        def run_selected() -> None:
            picked = list(tree.selection())
            if not picked:
                messagebox.showinfo("선택 필요", "전사/재조립할 항목을 하나 이상 선택해 주세요.", parent=dialog)
                return
            selected.extend(Path(targets[int(iid)]["folder"]) for iid in picked)
            dialog.destroy()

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="전체 선택", command=select_all).pack(side="left")
        ttk.Button(buttons, text="선택 실행", command=run_selected).pack(side="right")
        ttk.Button(buttons, text="취소", command=dialog.destroy).pack(side="right", padx=(0, 6))

        dialog.wait_window()
        return selected

    def show_button_help(self) -> None:
        messagebox.showinfo(
            "버튼 기능 안내",
            "\n".join(
                [
                    "EBS 현황 확인: 선택한 시험 구분/과목에서 받을 수 있는 문제, 빠른 정답, 해설을 표에 표시합니다.",
                    "가능 항목 전체 선택: 표에서 현재 다운로드 가능한 항목만 한 번에 선택합니다.",
                    "선택 다운로드: 표에서 선택한 가능 항목만 다운로드 원본 폴더에 저장합니다.",
                    "선택 항목 저장: 다운로드 원본 폴더의 파일을 사용자가 지정한 저장 경로로 복사합니다.",
                    "저장 경로 열기: 복사 결과를 확인할 폴더를 엽니다.",
                    "다운로드 원본 전사/재조립: 다운로드한 시험 폴더를 하나 이상 선택한 뒤, 문제/해설 PDF 옆에 '6월 전사 및 조립' 같은 폴더를 만들고 Markdown, HTML, DOCX로 변환합니다.",
                    "재조립 결과 열기: 과목 다운로드 원본 폴더를 엽니다.",
                    "재조립 로그 열기: 전사/재조립 과정의 로그를 엽니다.",
                    "환경 점검: EBSi 접속, 네트워크, 폴더 상태를 확인합니다.",
                    "관리 대상 폴더 확인: 사용자가 시험 자료를 총괄 배치할 폴더를 엽니다.",
                    "관리 대상 점검: 관리 대상 폴더를 스캔하고 보유 현황 보고서를 만듭니다.",
                    "공식 다운로드 새로고침: 선택 과목의 전체 범위를 다시 확인하고 가능한 파일을 일괄 다운로드합니다.",
                    "누락/재다운로드 보고서: 현재 보유분과 공식 원본을 대조합니다.",
                    "누락 보고서 기준 반영: 누락 보고서에 잡힌 파일을 지정한 저장 경로로 복사합니다.",
                    "보고서 확인: 보고서 폴더를 엽니다.",
                ]
            ),
        )

    def years_args(self) -> list[str]:
        return academic_years(self.config, include_future=self.include_future.get())

    def sessions_args(self) -> list[str]:
        subject = self._selected_subject()
        return self._subject_sessions(subject) or self._default_sessions_for_subject(subject)

    def run_async(self, title: str, command: list[str], allow_fail: bool = False) -> None:
        self.save_paths()
        thread = threading.Thread(target=self._run_command, args=(title, command, allow_fail), daemon=True)
        thread.start()

    def _run_command(self, title: str, command: list[str], allow_fail: bool) -> None:
        self.status.set(f"실행 중: {title}")
        self.log_line("")
        self.log_line(f"> {title}")
        self.log_line(" ".join(f'"{item}"' if " " in item else item for item in command))
        try:
            process = subprocess.Popen(
                command,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.log_line(line.rstrip())
            code = process.wait()
            if code == 0 or allow_fail:
                self.status.set(f"완료: {title}")
            else:
                self.status.set(f"오류: {title} (코드 {code})")
                messagebox.showerror("실행 오류", f"{title} 작업이 실패했습니다. 로그를 확인해 주세요.")
        except Exception as exc:
            self.status.set(f"오류: {title}")
            self.log_line(f"{type(exc).__name__}: {exc}")
            messagebox.showerror("실행 오류", str(exc))

    def _subject_args(self) -> list[str]:
        subject = self._selected_subject()
        if not subject.get("enabled", True):
            raise ValueError(subject.get("note", "아직 지원하지 않는 과목입니다."))
        missing = [name for name in ("subject_id", "area_ord", "target_cd") if not subject.get(name)]
        if missing:
            raise ValueError(f"공식 다운로드 정보가 아직 비어 있습니다: {', '.join(missing)}")
        return [
            "--subject-id",
            subject["subject_id"],
            "--subject-name",
            self._official_subject_name(),
            "--area-ord",
            subject["area_ord"],
            "--target-cd",
            subject["target_cd"],
            "--exam-family",
            subject.get("adapter", "kice"),
        ]

    def _base_official_command(self, out_path: Path) -> list[str]:
        return [
            sys.executable,
            "official_exam_sources.py",
            "--academic-years",
            *self.years_args(),
            "--sessions",
            *self.sessions_args(),
            *self._subject_args(),
            "--out",
            str(out_path),
        ]

    def _clear_availability(self) -> None:
        self.availability_rows = []
        for item in self.availability_tree.get_children():
            self.availability_tree.delete(item)

    def _load_availability(self, path: Path) -> None:
        self._clear_availability()
        if not path.exists():
            return
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        self.availability_rows = rows
        for index, row in enumerate(rows):
            state = "가능" if row.get("reachable") == "yes" else "미발견"
            self.availability_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(row["academic_year"], row["session"], row["doc_group"], state, row.get("title", "")),
            )

    def sort_availability(self, column: str) -> None:
        if not self.availability_rows:
            return

        session_order = {
            "3월": 1,
            "4월": 2,
            "5월": 3,
            "6월": 4,
            "7월": 5,
            "8월": 6,
            "9월": 7,
            "10월": 8,
            "11월": 9,
            "12월": 10,
            "수능": 11,
        }
        doc_order = {"문제": 1, "정답": 2, "해설": 3, "듣기": 4, "대본": 5}

        def sort_value(row: dict[str, str]):
            if column == "year":
                try:
                    return int(row.get("academic_year", "0"))
                except ValueError:
                    return 0
            if column == "session":
                return session_order.get(row.get("session", ""), 99)
            if column == "doc":
                return doc_order.get(row.get("doc_group", ""), 99)
            if column == "state":
                return 0 if row.get("reachable") == "yes" else 1
            if column == "title":
                return row.get("title", "")
            return ""

        reverse = not self.sort_reverse.get(column, False)
        self.sort_reverse[column] = reverse
        indexed = list(enumerate(self.availability_rows))
        indexed.sort(key=lambda item: (sort_value(item[1]), item[0]), reverse=reverse)
        for position, (index, _row) in enumerate(indexed):
            self.availability_tree.move(str(index), "", position)

    def check_availability(self) -> None:
        if not self._ensure_official_ready():
            return
        out_path = self._subject_sources_report("availability")

        def after() -> None:
            self._load_availability(out_path)
            available = sum(1 for row in self.availability_rows if row.get("reachable") == "yes")
            self.log_line(f"EBS 목록 갱신: {available}/{len(self.availability_rows)}개 가능")

        self.run_async_with_callback("EBS 현황 확인", self._base_official_command(out_path), allow_fail=True, callback=after)

    def run_async_with_callback(self, title: str, command: list[str], allow_fail: bool, callback) -> None:
        self.save_paths()
        thread = threading.Thread(target=self._run_command_with_callback, args=(title, command, allow_fail, callback), daemon=True)
        thread.start()

    def _run_command_with_callback(self, title: str, command: list[str], allow_fail: bool, callback) -> None:
        self._run_command(title, command, allow_fail)
        self.root.after(0, callback)

    def download_selected(self) -> None:
        if not self._ensure_official_ready():
            return
        self._ensure_download_folders()
        selected = list(self.availability_tree.selection())
        if not selected:
            messagebox.showinfo("선택 필요", "EBS 목록에서 다운로드할 행을 선택해 주세요.")
            return
        keys: list[str] = []
        for iid in selected:
            row = self.availability_rows[int(iid)]
            if row.get("reachable") != "yes":
                continue
            keys.append(f"{row['academic_year']}|{row['session']}|{row['doc_group']}")
        if not keys:
            messagebox.showinfo("다운로드 불가", "선택한 항목 중 현재 다운로드 가능한 항목이 없습니다.")
            return
        out_path = self._subject_sources_report("selected_download_sources")
        command = [
            *self._base_official_command(out_path),
            "--only-keys",
            *keys,
            "--download-dir",
            str(self._subject_download_dir()),
            "--legacy-dir",
            str(self._subject_legacy_dir()),
            "--archive-existing",
            "changed",
            "--manifest",
            str(self._subject_manifest("selected_download_manifest")),
            "--download",
        ]
        self.run_async("선택 다운로드", command, allow_fail=True)

    def select_all_available(self) -> None:
        available_iids = [
            str(index)
            for index, row in enumerate(self.availability_rows)
            if row.get("reachable") == "yes"
        ]
        self.availability_tree.selection_set(available_iids)

    def clear_availability_selection(self) -> None:
        self.availability_tree.selection_remove(self.availability_tree.selection())

    def copy_selected_to_save_path(self) -> None:
        selected = list(self.availability_tree.selection())
        if not selected:
            messagebox.showinfo("선택 필요", "EBS 목록에서 저장할 행을 선택해 주세요.")
            return

        keys: list[str] = []
        for iid in selected:
            row = self.availability_rows[int(iid)]
            if row.get("reachable") == "yes":
                keys.append(f"{row['academic_year']}|{row['session']}|{row['doc_group']}")

        if not keys:
            messagebox.showinfo("복사 불가", "선택한 항목 중 현재 복사 가능한 항목이 없습니다.")
            return
        self._ensure_copy_root()

        sources_report = self._subject_sources_report("availability")
        if not sources_report.exists():
            sources_report = self._subject_sources_report("official_sources")
        if not sources_report.exists():
            sources_report = self._subject_sources_report("selected_download_sources")
        if not sources_report.exists():
            messagebox.showinfo("보고서 필요", "먼저 EBS 현황 확인 또는 선택 다운로드를 실행해 주세요.")
            return

        command = [
            sys.executable,
            "copy_current_to_save_path.py",
            "--sources-report",
            str(sources_report),
            "--download-dir",
            str(self._subject_download_dir()),
            "--target-root",
            self.copy_root.get(),
            "--manifest",
            str(self._subject_manifest("copy_to_save_path_manifest")),
            "--only-keys",
            *keys,
        ]
        self.run_async("선택 항목 저장", command)

    def env_check(self) -> None:
        command = [sys.executable, "app_env_check.py"]
        if self.include_future.get():
            command.append("--include-future")
        self.run_async("환경 점검", command, allow_fail=True)

    def scan_status(self) -> None:
        command = [
            sys.executable,
            "exam_archive_manager.py",
            "--root",
            self.source_root.get(),
            "--out",
            str(self.config.reports_dir),
            "--hash",
            "--kice-start",
            str(self.config.academic_year_start),
            "--kice-end",
            str(academic_year_end(self.config, include_future=self.include_future.get())),
        ]
        self.run_async("관리 대상 점검", command)

    def refresh_downloads(self) -> None:
        if not self._ensure_official_ready():
            return
        self._ensure_download_folders()
        out_path = self._subject_sources_report("official_sources")
        command = [
            *self._base_official_command(out_path),
            "--download-dir",
            str(self._subject_download_dir()),
            "--legacy-dir",
            str(self._subject_legacy_dir()),
            "--archive-existing",
            "changed",
            "--manifest",
            str(self._subject_manifest("official_download_manifest")),
            "--download",
        ]
        self.run_async("공식 다운로드 새로고침", command, allow_fail=True)

    def make_gap_report(self) -> None:
        command = [
            sys.executable,
            "official_gap_plan.py",
            "--matrix",
            str(self.config.reports_dir / "kice_matrix.csv"),
            "--official",
            str(self.config.official_sources_report),
            "--out",
            str(self.config.latest_gap_report),
        ]
        self.run_async("누락/재다운로드 보고서", command)

    def apply_to_copy_root(self) -> None:
        if not messagebox.askyesno(
            "저장 경로 반영",
            "공식 다운로드 원본을 선택한 저장 경로로 복사합니다.\n기존 파일과 다른 파일이 있으면 중단됩니다.\n계속할까요?",
        ):
            return
        self._ensure_copy_root()
        command = [
            sys.executable,
            "apply_official_gap_plan.py",
            "--gap-plan",
            str(self.config.latest_gap_report),
            "--target-root",
            self.copy_root.get(),
            "--manifest",
            str(self.config.latest_apply_manifest),
            "--apply",
        ]
        self.run_async("저장 경로에 반영", command)


def main() -> None:
    root = Tk()
    try:
        root.call("tk", "scaling", 1.15)
    except Exception:
        pass
    app = ArchiveApp(root)
    app.log_line("준비되었습니다. 먼저 환경 점검을 실행해 주세요.")
    root.mainloop()


if __name__ == "__main__":
    main()
