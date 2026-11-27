# bakery-hnfsm-retiming

팀13: 베이커리 다목적 스케줄링 논문 구현 및 Retiming 기법 기반 개선. 연세대학교 IIE4124 「최적화이론및응용」(2026-2) 팀 프로젝트 저장소.

## 개요

- **선정 논문**: Babor, M., Paquet-Durand, O., Kohlus, R., Hitzmann, B. (2023). *Modeling and optimization of bakery production scheduling to minimize makespan and oven idle time*. Scientific Reports 13:235. DOI: [10.1038/s41598-022-26866-9](https://doi.org/10.1038/s41598-022-26866-9)
- **문제**: 중소규모 베이커리의 hybrid no-wait flow shop (HNFSM). 제품 그룹(g) 단위로 bowl time(WT)과 no-wait 조건을 지키면서, 대체 기계·오븐 구획·작업자(교대 근무시간)를 배정한다.
- **목적함수**: makespan과 oven idle time(OIDT)을 동시에 최소화하는 bi-objective 문제.
- **방법(논문)**: 다목적 메타휴리스틱(NSGA-II, SPEA2, GDE3, OMOPSO, SMPSO)이 연속 벡터를 만들고, SPV rule로 그룹 순서로 바꾼다. HNFSM decoder가 그 순서로 스케줄을 생성하고 (makespan, OIDT)를 평가한다.
- **팀 목표**:
  1. BK15·BK50 공개 데이터로 논문 결과를 재현한다.
  2. HNFSM 출력 스케줄에 그룹 단위 시각 이동 후처리(Group-Based Event-Point Retiming)를 추가해, makespan을 악화시키지 않고 OIDT를 줄이는지 검증한다(B0 vs P1).
- **팀원**: 김성우, 전제영, 한준희.

## 폴더 구조

```
bakery-hnfsm-retiming/
├── README.md               # 이 문서
├── AGENTS.md               # 에이전트용 작업 지침
├── pyproject.toml          # 패키지·의존성 정의 (uv). src/bakery를 설치형 패키지로 등록
├── uv.lock                 # 고정된 의존성 버전
├── .python-version         # 3.12
├── src/bakery/             # 모든 로직 (import bakery)
│   ├── paths.py            # 저장소 기준 경로 (data/, results/)
│   ├── preprocess.py       # 원본 Excel → 정제 JSON/XLSX (BK15, BK50)
│   ├── decoder.py          # SPV rule, instance 로드, HNFSM decoder, OIDT(합집합)
│   ├── checker.py          # 독립 스케줄 검증기 (M1–M19)
│   ├── retiming.py         # 독립 Event-Point Retiming, 준비 객체 API
│   ├── retiming_audit.py   # 독립 전수탐색 및 기존 파일럿 매핑
│   ├── cpsat.py            # CP-SAT 최소 makespan 모델
│   ├── problem.py          # jMetalPy 문제 클래스 (벡터 → SPV → decoder)
│   └── io.py               # 결과 저장/로드 (meta: 시각, Python, git rev)
├── experiments/            # 실행 스크립트. 결과를 results/<실험명>/에 저장
├── results/                # 실험 결과 (summary.json, 스케줄 csv)
├── notebooks/              # 저장된 결과를 보는 용도로만 사용
│   └── stage1-results.ipynb
├── tests/                  # pytest 회귀 테스트 (+ tests/data/paper-table1-example.json)
├── data/
│   ├── raw/                # Mendeley 원본 Excel (BK15, BK50, BK20)
│   └── processed/          # 정제본 bk15-clean / bk50-clean (.json, .xlsx)
├── paper/
│   ├── s41598-022-26866-9.pdf                           # 원논문 (기준 문서)
│   └── babor2023-bakery-scheduling-makespan-oven-idle.md  # 편의용 md 변환본
└── docs/
    ├── PROJECT.md          # 과제 요구 목차, 팀 범위·실험 계획·수행 순서, Retiming 아이디어 요약
    ├── PROGRESS.md         # 진행 현황, 핵심 수치, 알려진 문제, 전처리 결정
    ├── TODO.md             # 팀 결정 사항, Stage 2 전 필수 수정, 남은 작업
    ├── paper-conformance.md  # 원논문 대비 구현 적합성 검토
    ├── proposal/           # team13-proposal.pdf, Retiming 개선안 명세
    └── notes/              # 팀원 전처리 노트 (docx)
```

## 환경 설정

[uv](https://docs.astral.sh/uv/)로 프로젝트 루트에 `.venv` 하나를 만든다. 스크립트, 테스트, 노트북 커널 모두 이 환경을 쓴다.

```bash
uv sync                 # .venv 생성 + 의존성 설치 + bakery 패키지 editable 설치
```

- `src/bakery`가 패키지로 설치되므로 어느 폴더에서 실행해도 `import bakery`가 된다. `sys.path` 조작이나 상대경로가 필요 없다.
- 데이터·결과 경로는 `bakery.paths`가 저장소 루트 기준으로 계산한다.
- 노트북 커널: VS Code는 `.venv/bin/python`을 커널로 고른다. Jupyter Lab은 `uv run jupyter lab`으로 띄우면 `.venv` 커널(`python3`)을 쓴다.

## 실행

```bash
uv run python experiments/preprocess-data.py          # data/processed/*-clean.* 재생성
uv run python experiments/stage1-baseline.py          # 원래 순서 + random SPV, checker 검증
uv run python experiments/stage1-cpsat-bk15.py        # BK15 CP-SAT 최소 makespan
uv run python experiments/stage1-local-search-demo.py # swap local search 데모
uv run python experiments/stage1-nsga2-demo.py        # NSGA-II 연동 데모 (Table 5 설정 아님)
uv run pytest                                         # 회귀 테스트
```

결과는 `results/<실험명>/`에 저장되고, `notebooks/stage1-results.ipynb`에서 확인한다.

## 문서

- 프로젝트 지침과 계획: [docs/PROJECT.md](docs/PROJECT.md)
- 진행 현황: [docs/PROGRESS.md](docs/PROGRESS.md)
- 할 일과 결정 사항: [docs/TODO.md](docs/TODO.md)
- 원논문 적합성 검토: [docs/paper-conformance.md](docs/paper-conformance.md)
- Retiming 개선안 명세: [docs/proposal/proposal-idea-01-event-point-retiming.md](docs/proposal/proposal-idea-01-event-point-retiming.md)
- Retiming 최종 API·검증·재현 및 공유 범위: [docs/retiming.md](docs/retiming.md)

## 데이터 출처

Babor, M., Hitzmann, B. (2022). *Small and medium-sized bakery production data for scheduling*. Mendeley Data (CC BY 4.0). `data/raw/`의 BK15·BK50·BK20 Excel은 이 데이터셋에서 받은 원본이며 파일명을 바꾸지 않았다. 공개본은 원 생산 데이터를 일부 수정한 것이라 논문에 적힌 규모와 다른 부분이 있다(예: BK50 오븐 구획 10개 → 파일에는 9개).
