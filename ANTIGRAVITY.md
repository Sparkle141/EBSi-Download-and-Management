# Antigravity Guide

Antigravity에서 이 프로젝트를 열 때의 짧은 안내입니다. 자세한 공통 지침은 `AGENTS.md`를 따르세요.

## Recommended Context

- `README.md`: 사용자가 보는 기능, 버튼, Disclaimer
- `AGENTS.md`: 에이전트 공통 작업 규칙
- `subjects.json`: 과목/영역/세션 범위
- `test_crawl_and_reassemble/README.md`: 전사 및 재조립 모듈 설명

## Safe Task Shape

- 코드와 문서만 수정합니다.
- 실제 시험 파일, 다운로드 결과, 전사 산출물은 커밋하지 않습니다.
- 네트워크 조회가 필요한 경우 EBSi smoke test만 짧게 수행합니다.
- 사용자가 원하면 beta 상태로 커밋/푸시하고, release는 만들지 않습니다.

## AI Agent Reassembly

문제, 해설, 영어 대본을 문항 단위로 맞출 때는 로컬 코드 결과를 초안으로 보고 Antigravity의 시각/문서 검수 기능으로 보강하세요. 말풍선, 표 내부 텍스트, 스캔본 OCR은 반드시 검토 메모와 함께 남깁니다.
