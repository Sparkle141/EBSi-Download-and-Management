# Agent Guide

이 저장소는 EBSi 기출문제 탭의 공식 자료를 사용자가 직접 내려받아 정리하도록 돕는 베타 도구입니다. Codex, Claude Code/Cowork, Google Antigravity 같은 AI Agent 환경에서 폴더를 마운트해 작업할 때는 이 문서를 우선 컨텍스트로 사용하세요.

## Must Respect

- 실제 시험 문제, 빠른 정답 이미지, 해설 PDF, 영어 듣기 MP3, 대본 PDF를 저장소에 커밋하지 마세요.
- 대한민국 평가원, 대한민국 교육청, EBSi의 저작권을 존중한다는 README의 Disclaimer를 유지하세요.
- `downloads/`, `reports/`, `test_crawl_and_reassemble/output/`, `test_crawl_and_reassemble/intermediate/`, `test_crawl_and_reassemble/logs/`, `test_crawl_and_reassemble/system/packages/`는 로컬 산출물입니다.
- 사용자가 명시하지 않는 한 릴리스 생성은 보류하세요. 현재 상태는 beta입니다.

## Main User Workflow

1. 사용자는 `KICE_시험자료_관리_UI.vbs`를 실행합니다.
2. `시험 구분`에서 평가원 또는 교육청을 선택합니다.
3. `과목`을 선택합니다.
4. `EBS 현황 확인`으로 받을 수 있는 자료를 확인합니다.
5. 표에서 항목을 선택한 뒤 `선택 다운로드`를 누릅니다.
6. `선택 항목 저장`으로 원하는 저장 경로에 복사합니다.
7. 필요하면 `다운로드 원본 전사/재조립`으로 `test_crawl_and_reassemble` 산출물을 만듭니다.

## Important Files

- `kice_archive_gui.py`: 일반 사용자용 GUI 본체
- `official_exam_sources.py`: EBSi 공식 목록 조회 및 다운로드
- `subjects.json`: 과목, 영역, EBSi subject id, 평가원/교육청 세션 범위
- `copy_current_to_save_path.py`: 다운로드 원본을 저장 경로로 복사
- `test_crawl_and_reassemble/system/pipeline_runner.py`: PDF 전사 및 재조립 파이프라인
- `test_crawl_and_reassemble/system/pdf_to_markdown.py`: PDF 텍스트/에셋 전사
- `test_crawl_and_reassemble/system/assembler_docx.py`: DOCX 재조립
- `README.md`: 사용자용 설명과 Disclaimer

## Agent Mode Expectations

- AI Agent 모드에서는 문제 PDF, 해설 PDF, 영어 대본 PDF를 함께 보고 문항 단위로 검수/재조립할 수 있습니다.
- 로컬 코드만으로는 말풍선, 복잡한 표 내부 텍스트, 스캔본 OCR이 불완전할 수 있습니다.
- 영어 듣기 MP3는 저장만 하고 음성 전사를 시도하지 마세요. 제공 대본 PDF를 사용하세요.
- 그림/표에서 추출한 텍스트는 검토 가능하도록 해당 에셋 아래 또는 에셋 텍스트 섹션에 구분자를 두고 배치하세요.
- 산출물에는 처리 로그, 원본 경로, 한계, AI Agent 검수 메모를 `AI metadata`로 남기는 방향을 유지하세요.

## Validation Commands

가능하면 변경 후 아래를 확인하세요.

```powershell
python -m json.tool subjects.json > $null
python -m py_compile official_exam_sources.py kice_archive_gui.py test_crawl_and_reassemble/system/pipeline_runner.py test_crawl_and_reassemble/system/pdf_to_markdown.py test_crawl_and_reassemble/system/assembler_docx.py
```

EBSi 실조회가 필요한 변경은 네트워크가 필요합니다.

```powershell
python official_exam_sources.py --academic-years 2026 --sessions 수능 --subject-id 80003 --subject-name "영어" --area-ord 3 --target-cd D300 --exam-family kice --out reports/smoke_english_sources.csv --timeout 12
```

## Editing Notes

- 기존 사용자 경로가 들어간 `subjects.json` 항목은 임의로 지우지 마세요.
- 과목 범위는 평가원/교육청 모두 국어, 수학, 영어, 한국사, 사회탐구, 과학탐구, 직업탐구, 제2외국어/한문을 목표로 합니다.
- 평가원은 월별 목록 전체를 확인하되 제목으로 모의평가/수능을 분류합니다.
- 교육청은 3월, 4월, 5월, 7월, 10월 학력평가를 기본 추적합니다.
- README는 한국인 교사/학생 사용자가 바로 눌러볼 수 있는 버튼 중심 설명을 우선합니다.
