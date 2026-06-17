# Reassembly Agent Guide

이 디렉토리는 본편 EBSi 다운로더와 분리된 PDF 전사 및 재조립 모듈입니다. 이 폴더만 Codex, Claude Code/Cowork, Antigravity 등에 마운트한 경우에도 아래 원칙을 따르세요.

## Scope

- 입력: 사용자가 로컬에서 내려받은 문제 PDF, 해설 PDF, 영어 대본 PDF
- 출력: Markdown, HTML, DOCX, asset index, manifest, AI metadata
- 제외: 실제 시험 자료의 저장소 커밋, 영어 듣기 MP3 음성 전사

## Commands

```powershell
python system/pipeline_runner.py --input ../downloads --output-dir output
```

패키지 자동 설치가 불편한 환경에서는 설정에서 `install_packages`를 끄거나 아래처럼 실행하세요.

```powershell
python system/pipeline_runner.py --input ../downloads --output-dir output --no-install-packages
```

## Output Rules

- 그림/표 주변 추출 텍스트는 검토 가능하게 에셋 아래 또는 별도 에셋 텍스트 섹션에 둡니다.
- 말풍선, 복잡한 표, 스캔본 OCR은 AI Agent 검수 대상으로 보고 한계를 명시합니다.
- 문제, 해설, 영어 대본을 문항 단위로 묶을 때는 원본 경로와 처리 메모를 `AI metadata`에 남깁니다.
- `output/`, `intermediate/`, `logs/`, `system/packages/`는 로컬 산출물이며 커밋하지 않습니다.
