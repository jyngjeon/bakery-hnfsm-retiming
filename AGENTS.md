# AGENTS.md: 코딩 에이전트 작업 지침

## 프로젝트 요약

- Babor et al. (2023, Scientific Reports 13:235)의 베이커리 hybrid no-wait flow shop 스케줄링(HNFSM)을 재현한다. 목적함수는 makespan과 OIDT의 bi-objective 최소화다.
- 평가 구조: 연속 벡터 → SPV rule → 그룹 순서 → HNFSM decoder → (makespan, OIDT).
- 재현 대상 알고리즘은 NSGA-II, SPEA2, GDE3, OMOPSO, SMPSO이고, 데이터는 공개된 BK15·BK50이다.
- 개선안은 NSGA-II + HNFSM 출력에 Group-Based Event-Point Retiming 후처리를 붙이는 것이며, B0 vs P1으로 비교한다.

## 저장소 구조

- `src/bakery/`: 모든 로직. 설치형 패키지이므로 `from bakery.decoder import ...`처럼 import한다.
  - `paths.py`(경로), `preprocess.py`(전처리), `decoder.py`(SPV, HNFSM decoder, OIDT), `checker.py`(독립 검증), `cpsat.py`(CP-SAT), `problem.py`(jMetalPy 문제), `io.py`(결과 저장/로드)
- `experiments/`: 실행 스크립트. 각 스크립트는 `results/<실험명>/`에 결과를 저장한다.
- `results/`: 실험 결과(`summary.json`, 스케줄 csv)
- `notebooks/`: 저장된 결과를 읽어 보여주는 용도
- `tests/`: pytest 회귀 테스트, `tests/data/`에 테스트용 소형 instance
- `data/raw/`: Mendeley 원본 Excel, `data/processed/`: 정제본(`*-clean.json`, `*-clean.xlsx`)
- `paper/`: 원논문 PDF(기준 문서)와 편의용 md 변환본
- `docs/PROJECT.md`: 과제 목차, 범위, 실험 계획, 일정, 역할
- `docs/PROGRESS.md`: 진행 현황, 모델링 가정, 데이터 처리 결정, 알려진 문제
- `docs/TODO.md`: 팀 결정 대기 항목, 필수 수정, 남은 작업
- `docs/paper-conformance.md`: 원논문 대비 구현 적합성 검토
- `docs/proposal/`: 제안서 PDF, Retiming 개선안 명세
- `docs/notes/`: 팀원 전처리 노트(docx)

## 기준 문서(source of truth)

- **원논문 PDF `paper/s41598-022-26866-9.pdf`가 최종 기준이다.** 논문 내용을 인용할 때는 PDF 쪽수와 식 번호를 적는다(예: "p.5, M2").
- `paper/babor2023-...md`는 JATS XML에서 변환한 편의본이다. 그림은 캡션만 있다. 수식이나 그림을 판단할 때는 PDF를 확인한다.
- 데이터의 기준은 `data/raw/`의 원본 Excel이다. `data/processed/`는 `experiments/preprocess-data.py`가 만든 파생물이며 직접 고치지 않는다.

## 표기와 용어

- 논문 표기를 그대로 쓴다: `g, p, s, k, l, PT, WT, ST, CT, O_{g,p,s,k}, O_{g,p,s,l}, start_k, end_k, start_l, end_l, M, V, U, E`, 식 번호 `M1–M19`, 그룹 기준 시작시각 `T_g`, `OIDT`, `makespan`.
- 문서 본문은 한국어로 쓰되, 기술·논문 용어는 영어 그대로 둔다(makespan, OIDT, no-wait, decoder, Pareto front 등).

## 코드 구조 규칙

- **로직과 실험은 모두 `.py`로 작성한다.** 재사용 로직은 `src/bakery/`, 실행·실험은 `experiments/`에 둔다.
- **노트북은 `results/`에 저장된 결과를 읽어 표·그림으로 보는 용도로만 쓴다.** 노트북 안에서 decoder를 돌리거나 실험 로직을 정의하지 않는다. 결과를 바꾸려면 스크립트를 다시 실행한다.
- 실험 스크립트는 맨 위 `CONFIG` dict에 설정(instance, seed, 알고리즘 파라미터 등)을 두고, `bakery.io.save_json`으로 config와 결과를 함께 저장한다.
- 경로는 `bakery.paths`(저장소 루트 기준)를 쓴다. 상대경로, `os.chdir`, `sys.path` 조작을 쓰지 않는다.
- 새 스케줄이나 해를 보고할 때는 `bakery.checker.verify_schedule`로 위반 0건을 확인한 뒤에 보고한다.
- decoder, 전처리, checker를 바꾸면 `uv run pytest`로 회귀 테스트를 돌린다. 기대값이 바뀌는 변경이면 이유를 `docs/PROGRESS.md`에 적고 테스트 기대값을 갱신한다.

## 파일 이름

- 파일명과 폴더명은 영문으로 쓴다.
- 새로 만드는 파일은 띄어쓰기나 `_` 대신 `-`를 쓴다(예: `stage2-nsga2-table5.py`, `bk15-clean.json`).
- 예외: Python 모듈(`src/bakery/*.py`)은 import해야 하므로 `-`를 쓸 수 없다. 한 단어 이름을 쓰고, 불가피하면 `_`를 쓴다.
- 예외: 테스트 파일은 pytest 수집 규칙에 맞춰 `tests/test_<대상>.py` 형식으로 `_`를 쓴다(예: `test_decoder.py`). 테스트용 데이터 파일(`tests/data/`)은 `-` 규칙을 따른다.
- `data/raw/`의 원본 파일명은 바꾸지 않는다.

## 작업 규칙

- 논문에 없는 모델링 가정을 도입하면 `docs/PROGRESS.md`의 "모델링 가정" 절에 기록한다. 아직 결정되지 않은 사항은 `docs/TODO.md` (A)에 기록한다.
- **`docs/TODO.md` (A) "팀 결정 필요" 항목은 임의로 정하지 말고 팀에 먼저 묻는다.** 대표 항목은 OIDT 정의, infeasible 처리, 자원 tie-break, co-baking 규칙, batch 전개, iteration 정의와 HV reference point다.
- 작업을 마치면 `docs/PROGRESS.md`와 `docs/TODO.md`를 갱신한다.

## 재현성

- 모든 실험은 seed를 고정하고, 실행 설정을 기록한다: 알고리즘, population, 평가 횟수, seed, 데이터 파일, OIDT 정의, 코드 버전(`save_json`이 git revision을 자동 기록).
- jMetalPy는 Python `random`과 `numpy.random`을 쓰므로 둘 다 seed를 고정한다.
- 계산 시간은 하드웨어가 다르므로 알고리즘 간 상대 비교로만 쓴다.

## Python 환경

- 프로젝트 루트의 `.venv` 하나만 쓴다. `uv sync`로 만들고(Python 3.12, `pyproject.toml` + `uv.lock`), 명령은 `uv run ...`으로 실행한다.
- 패키지를 추가할 때는 `uv add <pkg>`(개발용은 `uv add --dev <pkg>`)를 쓰고 `pyproject.toml`과 `uv.lock`을 함께 commit한다. `pip install`을 직접 쓰지 않는다.
- 노트북 커널은 `.venv`의 Python을 쓴다(VS Code: `.venv/bin/python` 선택, Jupyter: `uv run jupyter lab`).
- PDF를 읽을 때는 opendataloader-pdf를 쓴다(Java 필요).

## Git

- commit message는 영어로 쓴다.
- 비밀정보(API key, `.env` 등)와 대용량 생성 산출물(실험 raw 결과, 대형 로그)은 commit하지 않는다. `.gitignore`를 참고한다. `results/`의 요약 결과(`summary.json`, 스케줄 csv)는 노트북이 읽으므로 commit한다.
