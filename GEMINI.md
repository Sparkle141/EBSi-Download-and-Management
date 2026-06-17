# Gemini / Google Agent Guide

Google Antigravity 또는 Gemini 계열 에이전트에서 이 폴더를 마운트했다면 루트의 `AGENTS.md`를 프로젝트 지침으로 사용하세요.

## Antigravity 사용 흐름

1. 이 저장소 폴더를 workspace로 엽니다.
2. `README.md`와 `AGENTS.md`를 컨텍스트로 지정합니다.
3. 다운로드 자동화 작업은 `kice_archive_gui.py` 또는 `official_exam_sources.py`를 기준으로 진행합니다.
4. 전사/재조립 작업은 `test_crawl_and_reassemble/` 안에서만 수행합니다.
5. 실제 시험 자료와 로컬 산출물은 커밋하지 않습니다.

## Agent Guardrails

- 저작권 자료 재배포 금지 원칙을 유지하세요.
- `downloads/`, `reports/`, `test_crawl_and_reassemble/output/` 등 로컬 산출물은 검토만 하고 커밋하지 마세요.
- 영어 듣기 MP3는 저장 전용입니다. 음성 전사 대신 제공 대본 PDF를 사용하세요.
- AI Agent가 표/그림/말풍선 텍스트를 보강할 때는 원본 위치와 한계를 함께 기록하세요.
