# 시험지 스캔 및 재조립 딸깍_박승수

PDF 시험지를 한 번에 처리하는 통합 파이프라인입니다. 크롤러가 PDF를 텍스트, 표, 그림, 위치 메타데이터로 분해하고, 어셈블러가 같은 결과 폴더에서 HTML과 DOCX를 만듭니다.

## 경고

표에서 추출한 텍스트는 100% 복사된 것으로, 있는 그대로입니다.

그림에서 추출한 텍스트는 가상 대화, 4컷만화를 가리지 않습니다. 뒤섞일 수 있으므로 확인 필수!

## 사용 방법

1. `input` 폴더에 PDF 시험지를 넣습니다.
2. `run_exam_reassembler.vbs`를 더블클릭합니다.
3. 필요하면 입력 PDF 파일이나 출력 경로를 지정합니다.
4. `통합 실행`을 누릅니다.

UI 없이 바로 실행하려면 `run_exam_reassembler_silent.vbs`를 더블클릭합니다.

## EBSi 공식 다운로드 산출물 입력

EBSi 공식 시험자료 다운로더의 산출물 폴더를 입력으로 지정할 수 있습니다. `reports/selected_download_sources_*.csv`, `reports/official_sources_*.csv`, `reports/official_exam_sources*.csv`, `reports/availability_*.csv`가 함께 있으면 파일명 추측 대신 보고서의 `local_path`, `sha256`, `doc_group` 정보를 기준으로 문제지, 정답 이미지, 해설지를 한 시험 단위로 묶습니다.

기본 입력 대상은 `downloads/<프로필명>/current/...`의 `doc_group=문제` PDF입니다. 같은 시험의 `정답` 이미지와 `해설` PDF는 재조립 입력으로 다시 처리하지 않고, `metadata.json`, `llm_manifest.json`, `llm_manifest.md`에 공식 출처 메타데이터로 연결합니다.

정답이나 해설이 연결된 경우에는 `*.llm_bundle.md`도 함께 생성됩니다. 이 파일은 순수 문제 전사본 뒤에 공식 정답/해설 부록과 출처 JSON을 붙인 LLM 인계용 합본이며, 원래 `*.md` 전사본은 그대로 유지됩니다.

`legacy` 폴더는 기본적으로 제외됩니다. 비교나 회귀 추적이 필요할 때만 `pipeline_config.json`에서 `include_legacy_downloads`를 `true`로 바꿔 사용합니다.

## 폴더 구조

| 위치 | 내용 |
|---|---|
| `input/` | 기본 PDF 입력 폴더 |
| `intermediate/` | PDF에서 추출된 중간 결과물 |
| `output/` | 열람과 활용을 위한 최종 결과물 복사본 |
| `logs/` | 실행 로그와 마지막 실행 상태 |
| `system/` | 실행 코드와 자동 설치 패키지 위치 |

## 산출물

각 PDF마다 `intermediate/<시험지명>_YYYYMMDD_HHMMSS/`와 `output/<시험지명>_YYYYMMDD_HHMMSS/`가 만들어집니다.

| 파일/폴더 | 설명 |
|---|---|
| `*.md` | PDF 본문을 페이지와 2단 구조에 맞춰 정리한 텍스트 |
| `*.layout.json` | 페이지 크기, 2단 여부, 난해 페이지 감지 정보 |
| `*.assets.json` | 그림, 표, 스캔 페이지의 라벨, 페이지, 좌표, 파일 경로 |
| `*.lines.json` | 줄 단위 텍스트와 위치, 에셋 연결 정보 |
| `metadata.json` | 원본 PDF, 추정 시험 정보, 파일 경로, 산출물 요약 |
| `llm_manifest.json` | LLM 전달용 JSON 색인 |
| `llm_manifest.md` | LLM 전달용 사람이 읽기 쉬운 색인 |
| `*.llm_bundle.md` | 문제 전사 뒤에 공식 정답/해설 부록을 붙인 LLM 인계용 합본 |
| `*.assembled.html` | 브라우저에서 열람 가능한 조립 결과 |
| `*.assembled.questions.docx` | 문제 단위로 편집 가능한 DOCX |
| `assets/` | 추출된 그림과 표 PNG |

## 설정

`pipeline_config.json`에서 다음 값을 바꿀 수 있습니다.

| 설정 | 의미 |
|---|---|
| `input_dir` | 기본 입력 폴더 |
| `input_dirs` | 추가 입력 PDF 파일 또는 폴더 목록 |
| `output_dir` | 내부 output 저장 위치 |
| `external_output_dir` | 내부 output 산물을 복사할 출력 경로 |
| `make_html` | HTML 생성 여부 |
| `make_docx` | DOCX 생성 여부 |
| `docx_layout` | `questions`, `table`, `linear` 중 하나 |
| `asset_text` | DOCX에 에셋 주변 텍스트를 넣는 방식. 기본값은 `tables_only` |
| `install_packages` | 필요한 패키지를 `system/packages`에 자동 준비 |
| `ebsi_reports_mode` | EBSi 보고서 자동 인식 여부. 기본값은 `auto`, 끄려면 `off` |
| `include_legacy_downloads` | EBSi `legacy` 산출물 포함 여부. 기본값은 `false` |
| `make_llm_bundle` | EBSi 정답/해설이 연결된 경우 `*.llm_bundle.md` 생성 여부 |

한 PDF 안에 여러 시험일이 들어 있어도 한 문서로 전체 페이지를 보존해 처리합니다. 날짜별 자동 분할이 필요하면 추후 분할 규칙을 별도 단계로 추가하면 됩니다.
