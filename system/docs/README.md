# 생활과 윤리 자료 관리 도구

원본 iCloud 폴더를 바로 수정하지 않고, 먼저 현재 보유 상태를 점검하고 공식 경로에서 개별 시험 파일을 확보하기 위한 작업 공간입니다.

원본 폴더:

```text
C:\Users\Dell\iCloudDrive\수능및모의고사문제\생활과 윤리 및 윤리와 사상\생활과 윤리
```

크롤링 이미지와 산출물은 `019e1a50-b475-77b2-a7d9-0ecd53cc2ab8` 작업에서 코드로 만들어진 파생물로 기록합니다. 원본 PDF와 파생 산출물을 분리해서 관리하는 것이 이 작업의 기본 원칙입니다.

## 1. 현재 보유 상태 점검

```powershell
C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe exam_archive_manager.py --hash
```

생성되는 주요 보고서:

- `reports/summary.json`: 전체 파일 수, 확장자, 출처, 산출물 유형 요약
- `reports/inventory.csv`: 전체 파일 분류표
- `reports/duplicate_candidates.csv`: 중복 후보
- `reports/kice_matrix.csv`: 2014-2026학년도 평가원 6월/9월/수능 보유 현황

## 2. EBSi 공식 개별 파일 수집

KICE CDN 직접 링크는 과거 링크가 404가 나는 경우가 있어, 실제 파일 확보에는 EBSi 공식 기출문제 목록을 사용합니다.

공식 경로:

```text
https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd=D300
```

2026학년도 예시 세트만 받을 때:

```powershell
C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe official_exam_sources.py --academic-years 2026 --sessions 6월 9월 수능 --download
```

2014-2026학년도 전체 검증 세트를 받을 때:

```powershell
C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe official_exam_sources.py --academic-years 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026 --sessions 6월 9월 수능 --out reports/official_exam_sources_2014_2026_verified.csv --download-dir official_downloads_2014_2026_verified --manifest reports/official_download_manifest_2014_2026_verified.json --download
```

현재 검증 결과:

- 공식 후보: 117개
- 다운로드 및 파일 형식 검증 통과: 108개
- EBSi 목록에 별도 정답 이미지가 없는 항목: 9개
- 최종 파일 폴더: `official_downloads_2014_2026_verified/`
- 최종 출처표: `reports/official_exam_sources_2014_2026_verified.csv`
- 최종 검증 기록: `reports/official_download_manifest_2014_2026_verified.json`

남은 9개는 2014-2016학년도 6월/9월/수능의 별도 `정답` 이미지입니다. 해당 회차들은 공식 `해설` PDF가 확보되어 있어 정답 확인은 해설 PDF로 보완 가능합니다.

## 3. 현재 보유분 보강 계획표

현재 원본 폴더의 보유 상태와 공식 다운로드 파일을 맞대어, 무엇을 보강하면 되는지 계획표를 만듭니다.

```powershell
C:\Users\Dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe official_gap_plan.py
```

생성 파일:

- `reports/official_gap_plan_2014_2026.csv`

현재 계획표 기준:

- 보강 대상: 34개
- 공식 파일로 바로 보완 가능한 대상: 34개
- 원본 iCloud 폴더에는 아직 아무 파일도 복사하지 않음

## 4. 다음 단계

2026-05-18에 공식 보강 파일을 원본 iCloud 폴더에 반영했습니다.

반영 위치:

```text
C:\Users\Dell\iCloudDrive\수능및모의고사문제\생활과 윤리 및 윤리와 사상\생활과 윤리\[평가원]평가원 모의고사 생윤\[공식]평가원 개별파일 생윤 2014-2026
```

반영 결과:

- 복사된 파일: 87개
- 기존 파일 덮어쓰기: 없음
- 반영 기록: `reports/official_gap_apply_manifest.json`
- 반영 후 전체 스캔 파일 수: 1874개
- 반영 후 `reports/kice_matrix.csv`: 2014-2026학년도 평가원 6월/9월/수능 39칸 모두 `완비`
- 반영 후 보강 계획표: `reports/official_gap_plan_after_apply.csv`

## 5. 정리 후 재시행 기록

사용자가 비공식, 스캔, 합본 루트 파일을 정리한 뒤 2026-05-18에 다시 점검했습니다.

재시행 결과:

- 정리 직후 전체 스캔 파일 수: 1851개
- 사라진 시험 단위: 10개
- 재다운로드 가능 판정: 10개 모두 가능
- 실제 보강 파일: 21개
- 재보강 후 전체 스캔 파일 수: 1872개
- 재보강 후 `reports/kice_matrix.csv`: 2014-2026학년도 평가원 6월/9월/수능 39칸 모두 `완비`
- 정리 직후 보강 계획표: `reports/official_gap_plan_after_cleanup.csv`
- 재보강 반영 기록: `reports/official_gap_apply_manifest_after_cleanup.json`
- 재보강 후 보강 계획표: `reports/official_gap_plan_after_cleanup_apply.csv`

## 6. UI 실행기

새 UI 실행기:

```text
KICE_시험자료_관리_UI.vbs
```

이 실행기는 `kice_archive_gui.py`를 열어 간단한 화면을 제공합니다.

화면 기능:

- 환경 점검: EBSi 접속, 네트워크, 원본 폴더, 다운로드 원본 폴더 확인
- 과목 선택: EBSi 평가원 사회탐구 과목을 선택
- 가능여부 확인: 공식 사이트에서 현재 받을 수 있는 시험/문서 목록을 표로 표시
- 선택 다운로드: 표에서 고른 항목만 다운로드
- 가능항목 표: 여러 행 선택 가능, 머리글 클릭으로 학년도/회차/문서/상태/공식 제목 정렬 가능
- 선택 이후 절차: 가능여부 목록 아래에서 선택 다운로드, 누락 보고서, 저장 경로 반영을 진행
- 선택 항목 저장 경로에 복사: 다운로드 원본 `current`에서 선택한 항목을 지정 저장 경로로 복사
- 버튼 기능 안내: 각 버튼의 역할을 UI에서 확인
- 원본 저장 폴더 확인
- 현황점검/분류
- 공식 다운로드 새로고침: 선택 과목의 점검 범위 전체를 새로 확인
- 누락/재다운로드 보고서 생성
- 저장 경로 지정: 실제로는 공식 다운로드 원본을 해당 경로로 복사
- 보고서 폴더 열기
- 저장 경로 열기

`다음 학년도까지 확인`을 켜면 현 시행연도 기준으로 평가원은 다음 학년도까지 확인합니다. 예를 들어 2026년에 시행되는 평가원 시험은 `2027학년도` 시험으로 다룹니다. 교육청 확장 시에는 교육청 공식 제목과 현 시행연도 명칭을 따로 따릅니다.

다운로드 범위는 두 층으로 정합니다.

- 기본 범위: `archive_config.json`의 `academic_year_start`, `academic_year_end`
- 확장 범위: UI에서 `다음 학년도까지 확인`을 켰을 때 현재 연도 기준 `평가원 = 현재 연도 + 1 학년도`

따라서 2026년에 실행하면 기본은 2014-2026학년도이고, 확장 확인을 켜면 2027학년도까지 확인합니다. 아직 공식 업로드 전이면 `미발견`으로 표와 보고서에 남습니다.

다운로드 원본 저장 정책:

- 과목별 최신 원본: `downloads/생활과 윤리/current/`
- 과거 원본 이관: `downloads/생활과 윤리/legacy/YYYYMMDD-HHMMSS/`
- 같은 파일을 다시 받으면 해시가 같으므로 새 파일을 만들지 않고 `unchanged`로 기록
- 같은 파일명인데 내용이 바뀌면 기존 파일만 `legacy`로 이관하고 새 파일을 `current`에 둠
- 매번 무조건 복사본을 쌓는 방식은 쓰지 않음

주 설정 파일:

```text
archive_config.json
```

확장 설계 메모:

```text
EXTENSION_PLAN.md
```

환경 점검과 과목/기관 라우팅 설명:

```text
ENVIRONMENT_AND_ROUTING.md
```

안정판 redist와 교육청 실험 어댑터:

```text
EXPERIMENTAL_OFFICE_ADAPTER.md
```

## 7. 기존 VBS 실행기

더블클릭용 실행기:

```text
생활과윤리_자료관리_실행기.vbs
```

실행기 메뉴:

- `1`: 현황점검 및 분류
- `2`: 2014-2026학년도 EBSi 공식 다운로드 새로고침
- `3`: 누락/재다운로드 가능 보고서 생성
- `4`: 누락 공식 파일을 원본 iCloud 폴더에 반영
- `5`: 전체 재시행
- `6`: 보고서 폴더 열기
- `7`: 도구 폴더 열기

`4`와 `5`는 원본 iCloud 폴더에 파일을 추가할 수 있으므로 실행기에서 확인 창을 띄웁니다. 기존 파일 덮어쓰기는 Python 반영 도구가 막습니다.

다음 단계 후보:

- 크롤링 산출물과 공식 원본 파일의 관계를 별도 인덱스로 정리
- 교육청 학평 폴더도 같은 방식으로 공식 개별 파일/파생 산출물 분리
- 중복 후보 보고서를 기준으로 실제 중복 정리 계획 수립
