# EBSi 자료 관리 내부 문서

이 문서는 배포 저장소 안에서 상대 경로 기준으로 동작하는 관리 도구 설명입니다. 개인 PC의 절대 경로, iCloud 경로, 특정 사용자 이름은 저장소에 넣지 않습니다.

## 기본 경로

- 관리 대상 폴더 기본값: `downloads/<과목>/current`
- 저장 경로 기본값: `exports/<과목>`
- 보고서 폴더: `reports`
- 전사/재조립 작업 폴더: `test_crawl_and_reassemble`

사용자는 GUI에서 `관리 대상 폴더`와 `저장 경로`를 자기 환경에 맞게 다시 지정할 수 있습니다.

## 현재 보유 상태 점검

```powershell
python exam_archive_manager.py --root "downloads/생활과 윤리/current" --hash
```

생성되는 주요 보고서:

- `reports/summary.json`
- `reports/inventory.csv`
- `reports/duplicate_candidates.csv`
- `reports/kice_matrix.csv`

## EBSi 공식 개별 파일 수집

공식 경로:

```text
https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd=D300
```

평가원 영어 수능 예시:

```powershell
python official_exam_sources.py --academic-years 2026 --sessions 수능 --subject-id 80003 --subject-name "영어" --area-ord 3 --target-cd D300 --exam-family kice --out reports/smoke_english_sources.csv
```

교육청 생활과 윤리 예시:

```powershell
python official_exam_sources.py --academic-years 2025 --sessions 3월 4월 5월 7월 10월 --subject-id 63002 --subject-name "생활과 윤리" --area-ord 5 --target-cd D300 --exam-family office --out reports/office_life_ethics_sources.csv
```

다운로드까지 수행하려면 `--download`, `--download-dir`, `--manifest`를 함께 지정합니다.

## 누락/재다운로드 계획

```powershell
python official_gap_plan.py --out reports/official_gap_plan_latest.csv
python apply_official_gap_plan.py --gap-plan reports/official_gap_plan_latest.csv --target-root "exports/생활과 윤리" --manifest reports/official_gap_apply_manifest_latest.json --apply
```

`apply_official_gap_plan.py`의 기본 저장 경로는 `exports/생활과 윤리`입니다. 실제 수업 자료 폴더에 반영하려면 GUI에서 저장 경로를 지정하거나 `--target-root`를 명시하세요.

## UI 실행기

더블클릭용 실행기:

```text
KICE_시험자료_관리_UI.vbs
```

이 실행기는 현재 사용자 환경에서 Python을 탐색합니다.

탐색 순서:

- 프로젝트 `.venv`
- `%LOCALAPPDATA%\Python\bin`
- 일반 Python 설치 폴더
- 현재 사용자 Codex runtime
- PATH

런처만 점검하려면 아래 환경 변수를 사용합니다.

```powershell
$env:EBSI_LAUNCHER_DRY_RUN='1'
cscript //Nologo "KICE_시험자료_관리_UI.vbs"
```

## 공개 저장소 원칙

- 실제 시험 문제, 빠른 정답 이미지, 해설 PDF, 영어 듣기 MP3, 대본 PDF는 저장소에 커밋하지 않습니다.
- `downloads`, `reports`, `exports`, `test_crawl_and_reassemble/output`은 로컬 산출물로 취급합니다.
- 특정 사용자 계정명이나 클라우드 폴더 경로를 기본값으로 넣지 않습니다.
