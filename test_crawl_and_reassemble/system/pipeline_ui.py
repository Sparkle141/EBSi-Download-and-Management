from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
import tkinter as tk

import pipeline_runner


ROOT_DIR = Path(__file__).resolve().parents[1]
WARNING_TEXT = (
    "표에서 추출한 텍스트는 100% 복사된 것으로, 있는 그대로입니다.\n"
    "그림에서 추출한 텍스트는 가상 대화, 4컷만화를 가리지 않습니다. 뒤섞일 수 있으므로 확인 필수!"
)


class PipelineApp(tk.Tk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = pipeline_runner._load_or_create_config(config_path)
        self.title("시험지 스캔 및 재조립 딸깍_박승수")
        self.geometry("760x520")
        self.minsize(720, 480)

        self.input_dir_var = StringVar(value=str(self.config.get("input_dir") or "input"))
        input_dirs = self.config.get("input_dirs") or []
        self.extra_input_var = StringVar(value=str(input_dirs[0]) if input_dirs else "")
        self.output_dir_var = StringVar(value=str(self.config.get("output_dir") or "output"))
        self.external_output_var = StringVar(value=str(self.config.get("external_output_dir") or ""))
        self.make_html_var = BooleanVar(value=bool(self.config.get("make_html", True)))
        self.make_docx_var = BooleanVar(value=bool(self.config.get("make_docx", True)))
        self.install_var = BooleanVar(value=bool(self.config.get("install_packages", True)))
        self.open_output_var = BooleanVar(value=bool(self.config.get("open_output", False)))
        self.status_var = StringVar(value="PDF를 input 폴더에 넣거나, 추가 입력 폴더를 지정한 뒤 실행하세요.")

        self._build()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(9, weight=1)

        title = ttk.Label(container, text="시험지 스캔 및 재조립 딸깍_박승수", font=("", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        warning = ttk.Label(container, text=WARNING_TEXT, foreground="#9a3412", justify="left")
        warning.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self._path_row(container, 2, "기본 input 폴더", self.input_dir_var, self._choose_input_dir)
        self._path_row(container, 3, "입력 PDF 파일", self.extra_input_var, self._choose_extra_input_file)
        self._path_row(container, 4, "내부 output 폴더", self.output_dir_var, self._choose_output_dir)
        self._path_row(container, 5, "출력 경로", self.external_output_var, self._choose_external_output_dir)

        options = ttk.Frame(container)
        options.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        ttk.Checkbutton(options, text="HTML 만들기", variable=self.make_html_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(options, text="DOCX 만들기", variable=self.make_docx_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(options, text="필요 패키지 자동 준비", variable=self.install_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(options, text="완료 후 폴더 열기", variable=self.open_output_var).pack(side="left")

        env_buttons = ttk.Frame(container)
        env_buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        self.check_env_button = ttk.Button(env_buttons, text="환경 점검", command=self._check_environment)
        self.check_env_button.pack(side="left")
        self.install_pkg_button = ttk.Button(env_buttons, text="필수 패키지 설치", command=self._start_install_packages)
        self.install_pkg_button.pack(side="left", padx=(8, 0))

        buttons = ttk.Frame(container)
        buttons.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Button(buttons, text="input 폴더 열기", command=lambda: self._open_path(self.input_dir_var.get())).pack(side="left")
        ttk.Button(buttons, text="output 폴더 열기", command=lambda: self._open_path(self.output_dir_var.get())).pack(side="left", padx=(8, 0))
        self.run_button = ttk.Button(buttons, text="통합 실행", command=self._start)
        self.run_button.pack(side="right")

        log_frame = ttk.LabelFrame(container, text="진행 상태", padding=10)
        log_frame.grid(row=9, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Label(log_frame, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.log_text = tk.Text(log_frame, height=10, wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.log_text.configure(state="disabled")

    def _path_row(self, parent: ttk.Frame, row: int, label: str, var: StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=4)
        ttk.Button(parent, text="선택", command=command).grid(row=row, column=2, sticky="e", pady=4)

    def _choose_input_dir(self) -> None:
        self._choose_dir_into(self.input_dir_var, "기본 input 폴더 선택")

    def _choose_extra_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="입력 PDF 파일 선택",
            filetypes=[("PDF 파일", "*.pdf"), ("모든 파일", "*.*")],
        )
        if path:
            self.extra_input_var.set(path)

    def _choose_output_dir(self) -> None:
        self._choose_dir_into(self.output_dir_var, "내부 output 폴더 선택")

    def _choose_external_output_dir(self) -> None:
        self._choose_dir_into(self.external_output_var, "출력 경로 선택")

    def _choose_dir_into(self, var: StringVar, title: str) -> None:
        path = filedialog.askdirectory(title=title)
        if path:
            var.set(path)

    def _start(self) -> None:
        self._save_config()
        self._set_buttons_enabled(False)
        self.status_var.set("실행 중입니다. PDF가 많으면 시간이 걸릴 수 있습니다.")
        self._log("통합 실행을 시작했습니다.")
        thread = threading.Thread(target=self._run_worker, daemon=True)
        thread.start()

    def _run_worker(self) -> None:
        try:
            code = pipeline_runner.main(["--config", str(self.config_path)])
        except Exception as exc:
            self.after(0, self._done, 1, str(exc))
            return
        status_path = ROOT_DIR / "logs" / "last_run_status.txt"
        detail = status_path.read_text(encoding="utf-8") if status_path.exists() else ""
        self.after(0, self._done, code, detail)

    def _done(self, code: int, detail: str) -> None:
        self._set_buttons_enabled(True)
        if code == 0:
            self.status_var.set("완료되었습니다.")
            self._log(detail.strip() or "완료")
            messagebox.showinfo("완료", "시험지 추출 재조립이 완료되었습니다.")
        else:
            self.status_var.set("실패했습니다. logs 폴더의 실행 로그를 확인해 주세요.")
            self._log(detail.strip() or "실패")
            messagebox.showerror("실패", "실행 중 문제가 발생했습니다. logs 폴더의 로그를 확인해 주세요.")

    def _check_environment(self) -> None:
        self._save_config()
        missing = pipeline_runner._missing_packages(self.config)
        if missing:
            message = "누락된 필수 패키지: " + ", ".join(missing)
            self.status_var.set("필수 패키지 설치가 필요합니다.")
            self._log(message)
            messagebox.showwarning("환경 점검", message)
            return

        self.status_var.set("필수 패키지가 준비되어 있습니다.")
        self._log("환경 점검 완료: 필수 패키지가 준비되어 있습니다.")
        messagebox.showinfo("환경 점검", "필수 패키지가 준비되어 있습니다.")

    def _start_install_packages(self) -> None:
        self._save_config()
        self._set_buttons_enabled(False)
        self.status_var.set("필수 패키지를 준비하는 중입니다.")
        self._log("필수 패키지 설치를 시작했습니다.")
        thread = threading.Thread(target=self._install_worker, daemon=True)
        thread.start()

    def _install_worker(self) -> None:
        log_dir = ROOT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"package_install_{datetime.now():%Y%m%d_%H%M%S}.log"
        try:
            with log_path.open("w", encoding="utf-8") as log:
                pipeline_runner._ensure_packages(self.config, log)
                pipeline_runner._reload_pdf_tools()
        except Exception as exc:
            self.after(0, self._install_done, 1, f"{exc}\n로그: {log_path}")
            return
        self.after(0, self._install_done, 0, f"필수 패키지 준비 완료\n로그: {log_path}")

    def _install_done(self, code: int, detail: str) -> None:
        self._set_buttons_enabled(True)
        if code == 0:
            self.status_var.set("필수 패키지 준비가 완료되었습니다.")
            self._log(detail)
            messagebox.showinfo("필수 패키지 설치", "필수 패키지 준비가 완료되었습니다.")
        else:
            self.status_var.set("필수 패키지 설치에 실패했습니다.")
            self._log(detail)
            messagebox.showerror("필수 패키지 설치", "설치에 실패했습니다. logs 폴더의 로그를 확인해 주세요.")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.run_button.configure(state=state)
        self.check_env_button.configure(state=state)
        self.install_pkg_button.configure(state=state)

    def _save_config(self) -> None:
        data = dict(self.config)
        data.update(
            {
                "input_dir": self.input_dir_var.get().strip(),
                "input_dirs": [self.extra_input_var.get().strip()] if self.extra_input_var.get().strip() else [],
                "output_dir": self.output_dir_var.get().strip() or "output",
                "external_output_dir": self.external_output_var.get().strip(),
                "make_html": self.make_html_var.get(),
                "make_docx": self.make_docx_var.get(),
                "install_packages": self.install_var.get(),
                "open_output": self.open_output_var.get(),
            }
        )
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.config = data

    def _open_path(self, value: str) -> None:
        path = pipeline_runner._resolve_path(Path(value or "."), ROOT_DIR)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main(argv: list[str] | None = None) -> int:
    config_path = ROOT_DIR / "pipeline_config.json"
    app = PipelineApp(config_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
