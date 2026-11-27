# 진행 현황 (2026-11-27 기준)

근거는 원본 노트북(`1단계.ipynb`, 리팩토링 후 삭제)의 저장된 출력, `docs/notes/`의 전처리 노트, 리팩토링 후 `experiments/`와 `tests/`로 다시 실행한 결과다.

> 현재 코드는 팀원이 `han/` 폴더로 전달한 자료다. 노트북은 팀원 개인 conda 환경에서 실행되었다.

## 1. 단계별 상태 (제안서 6.4 일정 대비)

| 단계 | 계획 기간 | 상태 | 내용 |
|---|---|---|---|
| 1. 데이터 정리, decoder, checker | 11/09–11/12 | **대부분 완료** | 전처리, HNFSM decoder, 독립 checker 동작. Table 1 예제는 테스트로 추가함. 미완: Gantt chart, makespan 하한 점검 |
| 2. 알고리즘 연결 | 11/13–11/16 | **일부** | NSGA-II를 Table 5 설정으로 연결(2026-11-27, 9절). SPEA2·GDE3·OMOPSO·SMPSO 미연결 |
| 3. 재현 실험 A | 11/17–11/20 | **일부** | NSGA-II R1/R2 완료, 지표 PDS·MSF·DPF·RHA 구현(9절). 나머지 4종, PCA + GMM, 통계 검정 없음 |
| 4. Retiming 구현·부분문제 검증 | 11/19–11/25 | **이 저장소에 없음** | 명세는 `docs/proposal/`에 있음. 제안서의 BK15 예비 검증 코드 위치 확인 필요 |
| 5. B0 vs P1, Ablation | 11/26–11/30 | 미착수 | |
| 6. 분석·보고서 | 12/1–12/7 | 미착수 | |

일정 대비 약 1단계 지연이다.

2026-11-27 계획 변경: NSGA-II로 구현·검증 → Retiming → B0 vs P1을 먼저 마치고, 나머지 알고리즘 4종은 그 뒤에 덧붙인다(PROJECT.md 7절, TODO.md (C)).

## 2. 현재 있는 것

**전처리 (`src/bakery/preprocess.py`, `experiments/preprocess-data.py`)**
- 원본 Excel을 machines, employees, operations 표로 분리해 `data/processed/bk{15,50}-clean.{json,xlsx}`를 만든다.
- 인덱스:
  - 연속 인덱스 `k`, `l`
  - 그룹 `g`. batch 전개분은 뒤 번호로 붙인다.
  - 작업 순서 `s`
- 작업 정보:
  - `resource_type`(NONE / EMPLOYEE / MACHINE / OVEN)
  - `eligible_k`, `eligible_l`

**CP-SAT (`src/bakery/cpsat.py`, `experiments/stage1-cpsat-bk15.py`)**
- BK15 전체 모델을 OR-Tools CP-SAT로 makespan만 최소화했다. 결과는 **OPTIMAL, makespan 471**이고 checker PASS다.
- OIDT는 최적화 대상이 아니라 실행마다 달라진다(원본 노트북 281, 리팩토링 후 seed 0 실행 206, 재실행 357). workers 8의 병렬 탐색 때문에 seed를 고정해도 같은 해가 나오지 않는다. makespan 471은 매번 같다.

**HNFSM decoder (`src/bakery/decoder.py`)**
- 구성: `spv_to_group_order`, `load_hnfsm_instance`, `hnfsm_decode`
- 방식: bitmask 기반이다. 그룹 시작시각 `T_g`를 1분 단위로 훑어 가장 이른 실행가능 시각에 그룹 전체를 배치한다. 자원은 first-fit(가장 낮은 인덱스)으로 고른다.
- 실패 처리: 배치에 실패하면 `(1e9, 1e9)`를 반환한다.

**NSGA-II 데모 (`src/bakery/problem.py`, `experiments/stage1-nsga2-demo.py`)**
- 설정: BK15, population 20, SBX 0.9, 200회 평가. 리팩토링하면서 seed 2001을 고정했다(원본은 seed 없음).
- 결과 front: 원본 (475, 180), (478, 154) / seed 2001 (475, 300), (478, 242), (493, 212), (494, 167), (503, 142)

**독립 checker (`src/bakery/checker.py`)**
- 검사 항목: 완전성, M6–M12, M15–M19, 목적함수 재계산
- BK15·BK50 원래 순서, CP-SAT 해, NSGA-II 데모 해 모두 PASS다.

**회귀 테스트 (`tests/`, 9개 통과)**
- 전처리 결과가 `data/processed/` JSON과 같은지
- 원래 순서 BK15 (519, 273), BK50 (1202, 2409)와 random SPV(seed 42) 결과가 원본 노트북과 같은지
- 논문 Table 3 SPV 예제, Table 1 예제(makespan 244, oven idle 53)
- UNLIMITED 기계 용량 무제한 처리

## 3. 핵심 수치

OIDT는 구획별 합집합 정의 기준이다.

| 항목 | BK15 | BK50 |
|---|---|---|
| 정제 후 그룹 / 작업 | 16 / 164 | 62 / 679 |
| 원래 순서 (makespan, OIDT) | (519, 273) | (1202, 2409) |
| 원래 순서 OIDT, 논문 M2 그대로 계산 | 187 | 1362 |
| CP-SAT 최소 makespan | 471 (OPTIMAL) | 미실행 |
| NSGA-II 데모 front (seed 2001) | (475, 300) … (503, 142), 5개 | – |
| NSGA-II Table 5, seed 10개 합친 front (9절) | (471, 119), (474, 86), (491, 74) | (960, 1956) … (1022, 1208), 7개 |
| random search 최소 makespan (검토 시 별도 재실행) | 474 (3000회) | 1057 (300회) |
| random 순서 중 infeasible 비율 | 3.4% (102/3000) | 0% (0/300) |
| decoder 1회 평가 시간 | 약 1.5 ms | 약 21 ms |
| 논문 PF* (Fig. 7, p.9) | E1≈(471, 93), E2≈(480, 72) | E2 OIDT 1243, E1→E2: makespan +61 / OIDT −1348, E1 ≈ (934, 2590) (Fig. 10a 판독, 본문 수치와 일치. 이전 판독 940–960) |

## 4. 데이터 처리 결정 (팀원 전처리)

**BK15**
- machine_id 결번(3, 5, 6)을 정리해 k=1..10으로 재부여했다.
- 오븐 4구획(Stone oven A1–A3, Baking chamber B)은 OVEN, Proving chamber는 UNLIMITED, 나머지 5대는 SINGLE로 분류했다.
- 표기 정리:
  - "Product 1"을 "Product 1A"로 통일
  - 공정명 대소문자 통일
  - "Mnaual"을 "Manual"로, "Cutting Machine"을 "Cutter"로 수정
  - 빈 자원 36건을 NONE으로 채움
- batch: Group 6(batches=2)의 2회차를 g=16으로 복제했다.

**BK50**
- 기계 표:
  - 기계 표의 Employee/Manual 더미 행(id 25)을 제거했다.
  - **machine_id 20(Oven 7)이 원본에 없어 오븐 구획이 9개다(논문은 10개).** k=1..23, 오븐은 k=14–22.
  - Retarder, Bun roller, Loaf divider, Loaf shaper는 어떤 작업에서도 쓰이지 않는다.
- **Group 31 분리**: p=2에 WT=15로 시작하는 5개 작업과 WT=30으로 시작하는 5개 작업이 함께 들어 있어, 뒤 묶음을 p=3 "Sourdough Bread-2"로 나눴다.
- **s≥2의 WT를 0으로 정규화**했다. 대상은 Group 5 p=2(34가 반복 기재)와 Group 22 p=1(206은 누적 PT와 같음)이다.
- 제품명 혼용 2건과 공정명 오타 약 10종을 통일했다(일부 변형, 예: "Kneading 1", "Transfer to freezer/freezing"은 남아 있음). 빈 자원 103건은 NONE으로 채웠다.
- **batch 전개**: batches=2인 그룹 12개와 batches=3인 그룹 5개에서 22개 그룹(g=41–62)이 추가되었다.
- **Group 18**: p=1 "Dough C"만 batches=1이다. 그룹 최댓값 기준으로 Dough C까지 함께 2회 전개했다.

## 5. 모델링 가정 (논문에 명시되지 않음)

2026-11-26 팀 결정으로 확정했다(TODO (A) A1–A6). 근거는 `docs/decisions-A.md`에 있다.

1. **OIDT는 구획별 점유구간 합집합 기준**으로 계산한다(제안서 5.3, A1).
   - 논문 M2를 그대로 쓰면 같은 그룹이 같이 굽는 작업의 PT가 두 번 차감되어, 최적화하면 OIDT가 음수까지 내려간다(BK15 −28).
   - 보고서에는 M2 그대로의 값을 병기한다.
2. **batch는 서로 독립된 그룹으로 전개**한다(A5).
   - 근거는 데이터셋 Description 시트의 "batches of same group do not depend on each other"이고, 논문에는 batch 언급이 없다.
   - 전개하지 않으면 BK50 makespan이 논문 E1과 규모부터 다르다(638 vs ≈ 940–960).
3. **자원 선택은 first-fit(가장 낮은 인덱스)** 이다(A3). 논문은 "based on availability"라고만 쓴다. 오븐 used_first·min_idle은 민감도 실험으로만 쓴다. B0·P1은 같은 규칙을 쓴다.
4. **같은 그룹 오븐 공동 사용은 겹침 형태에 제한이 없다**(A4). 동시 시작을 요구하지 않는다.
5. **`T_g`는 1분 단위로 탐색**하고 가장 이른 시각을 고른다.
6. **배치할 수 없는 순서는 `(1e9, 1e9)` penalty**를 준다(A2). 논문에는 언급이 없다. 알고리즘별 infeasible 발생률을 함께 보고한다.
7. **Group 18 Dough C를 2회 전개**하고(A5), **Group 31을 p=3으로 분리**했다.
8. **iteration은 세대 수**다(A6). population 50 × 300세대 = 15,000회 평가이고, 50·100·200·300세대 시점의 front를 저장한다.
9. **성능 비교 주 지표는 RHA**다(A6, 논문 Eq. 6). PF*는 같은 인스턴스에서 모든 알고리즘의 해를 합친 nondominated set이다. HV reference point는 [0, 1] 정규화 후 (1.1, 1.1)이다.
10. SBX와 polynomial mutation의 **distribution index는 20**(jMetalPy 기본값)이다. Table 5에 값이 없다.

## 6. 알려진 문제

- **[수정됨, 2026-11-24] UNLIMITED 기계 처리**
  - 원본 decoder는 UNLIMITED 기계(BK15 Proving chamber)를 쓰는 작업이 생기면 `KeyError`가 났고, CP-SAT은 UNLIMITED에도 NoOverlap을 걸었다.
  - 리팩토링하면서 decoder는 용량 검사 없이 첫 적격 기계를 배정하고, CP-SAT은 UNLIMITED에 제약을 걸지 않도록 고쳤다(`tests/test_decoder.py`). 현재 데이터에는 이런 작업이 없어 기존 결과는 그대로다.
- **[데이터] BK50 Group 31의 2회차 Boxing**은 원본 자원 칸이 비어 있어 NONE이 되었다. 1회차 Boxing은 Manual이다. Manual 누락으로 보인다.
- **[설정] NSGA-II 데모(`experiments/stage1-nsga2-demo.py`)** 는 Table 5 설정과 다르다(population 20, SBX 0.9). 원본 노트북은 seed가 없었고(`random_seed = 2001` 셀은 실행되지 않음), 리팩토링 후에는 seed 2001을 고정했다.
- **[문서] 원본 노트북 cell 14 markdown**은 "논문 BK15 PF* 최소 makespan 약 471분"을 논문 본문 수치처럼 썼다. 노트북은 삭제했으므로 보고서에 옮길 때 출처를 "팀 CP-SAT 결과, Fig. 7a 판독값과 일치"로 적는다.
- **[문서] 전처리 docx 3건**은 모두 2절부터 시작한다(1절 없음). 「결과판단」은 문서에 없는 "위 코드"를 언급한다.
- **[참고] decoder 내부 자원 선택**은 그룹 안 작업을 (p, s) 순서로 배정한다. 다른 배정이면 들어갈 수 있는 시각을 놓쳐 `T_g`가 늦어질 수 있다. 영향은 작다.
- **[참고] BK50 makespan 격차**: random search 최소 1057은 논문 E1(약 940–960)과 차이가 크다. 실제 최적화 후 다시 비교해야 한다.
  - 2026-11-27: NSGA-II Table 5(seed 10개) 최소 makespan은 960, seed 중앙값 986.5다. 논문 E1 ≈ 934(Fig. 10a 판독)보다 26분 길다. CP-SAT은 931(9절, 8절).

## 7. 코드 리팩토링 (2026-11-24)

- 원본 노트북 `1단계.ipynb`의 로직을 `src/bakery/`로 옮기고, 실행부는 `experiments/`로 나눴다. 노트북은 `notebooks/stage1-results.ipynb`(결과 보기 전용)로 대체하고 원본 노트북과 `checker.py`는 저장소에서 삭제했다(원본은 팀원 전달 폴더에 남아 있음).
- 셀 대응:

  | 원본 노트북 | 리팩토링 후 |
  |---|---|
  | cell 4, 6 (전처리) | `src/bakery/preprocess.py`, `experiments/preprocess-data.py` |
  | cell 8 (CP-SAT) | `src/bakery/cpsat.py`, `experiments/stage1-cpsat-bk15.py` |
  | cell 10 (BK50 프로토타입) | 삭제. 무결성 검사는 전처리 assert, 전처리 회귀 테스트(정제 JSON 일치), checker로 대체 |
  | cell 13 (decoder) | `src/bakery/decoder.py`, `experiments/stage1-baseline.py` |
  | cell 17 (local search 데모) | `experiments/stage1-local-search-demo.py` |
  | cell 20, 23 (jMetalPy) | `src/bakery/problem.py`, `experiments/stage1-nsga2-demo.py` (cell 20의 미완성 클래스는 삭제) |
  | cell 26, 28 (checker) | `src/bakery/checker.py` (메시지 영문화, 로직 동일) |

- 검증: 전처리 JSON이 원본과 바이트 단위로 같고, decoder 결과(BK15 519/273, BK50 1202/2409, random SPV 534/221, 1259/2866), local search 데모(528/155), CP-SAT makespan 471이 원본 노트북 출력과 같다.
- 동작 변경은 UNLIMITED 버그 수정과 NSGA-II 데모 seed 고정 두 가지다.
- 파일명 변경: `bk15_clean.*` → `bk15-clean.*`, 전처리 노트·제안서·Retiming 명세 파일명을 영문으로 바꿨다.
- 환경: `pyproject.toml` + `uv.lock`, 프로젝트 루트 `.venv` 하나로 통일했다(`requirements.txt` 삭제). 설치 버전: numpy 2.5.5, pandas 2.3.3, ortools 9.15, jmetalpy 1.9.0.

## 8. TODO (A) 결정 자료 실험 (2026-11-26)

- 목적: TODO (A) 항목별로 어느 선택이 논문 표현과 논문 PF*에 맞는지 확인했다. 결과와 판단은 `docs/decisions-A.md`에 있다. 결정은 아직 하지 않았다.
- 코드 추가. 기본값은 기존 동작과 같고, 회귀 테스트 14개가 통과한다(기존 9개 + 새 옵션 5개).
  - `decoder.hnfsm_decode(..., oven_rule, cobake, oidt)`
    - `oven_rule`: `first_fit` / `used_first` / `min_idle`
    - `cobake`: `any` / `same_start` / `same_start_end`
    - `oidt`: `union` / `m2`
    - `oidt_m2()`를 추가했다.
  - `cpsat.solve_min_makespan(..., cobake)`, 반환값에 `best_bound`와 `oidt_m2`를 추가했다.
  - `problem.BakerySchedulingProblem(path, **decode_kwargs)`
  - `bakery.variants`: batch 미전개와 BK50 Group 18 Dough C 1회 변형 인스턴스. `results/`에 쓰고 `data/processed/`는 건드리지 않는다.
- 실험: `experiments/a-decisions-cpsat.py`, `experiments/a-decisions-nsga2.py`(Table 5 설정, 15,000회 평가, BK15 seed 1–10, BK50 seed 1–3)
- 주요 수치:
  - M2를 최적화하면 BK15 OIDT가 음수(−28)가 된다.
  - BK50 base NSGA-II 최소 OIDT는 1243으로 논문 E2와 같다.
  - BK50 batch 미전개 시 makespan 638(NSGA-II), 569(CP-SAT)로 논문 E1 ≈ 940–960과 맞지 않는다.
  - BK50 CP-SAT(전개, 600초)는 makespan 931이다. 논문 E1보다 낮은 해가 있다.
  - NSGA-II(Table 5) 실행 중 infeasible 비율은 BK15 0.02%, BK50 0%다.
  - 1회 실행 시간(8 프로세스 병렬): BK15 약 50초, BK50 약 5–8분
- Table 5에는 SBX와 polynomial mutation의 distribution index가 없어 jMetalPy 기본값 20을 썼다.

## 9. Stage 2: NSGA-II Table 5 실행과 논문 대조 (2026-11-27)

- 스크립트 `experiments/stage2-nsga2.py`, 결과 `results/stage2-nsga2/`(`summary.json`, `fronts.csv`, `metrics.csv`, `trace.csv`), 보기 `notebooks/stage2-nsga2.ipynb`.
- 설정: Table 5(p.20) population 50, SBX rate 1, polynomial mutation 1/NG, binary tournament, distribution index 20. seed 1–10. 300세대 = 15,000회 평가. 50·100·200·300세대의 population nondominated front를 snapshot으로 저장했다.
  - **iteration 경계 정의(새 가정)**: 초기 population을 1세대로 센다. 따라서 g세대 = 50·g회 평가다(50세대 = 2,500회). `a-decisions-nsga2.py`의 15,000회 예산과 맞추기 위한 선택이고, 1세대 차이라 영향은 작다.
  - seed 1의 snapshot이 논문 방식(iteration별 1 run, R1)에 해당한다. 같은 seed로 50세대만 돌린 결과와 같다.
  - decoder 설정은 PROGRESS 5절 결정 그대로(OIDT 합집합, first-fit, 겹침 자유, batch 전개, 1e9 penalty).
- 새 코드
  - `src/bakery/metrics.py`: PDS(Eq. 2), MSF(Eq. 3), DPF(Eq. 4), HV(Eq. 5), RHA(Eq. 6). MSF는 논문에 인쇄된 식 그대로(분모가 후보 front 범위)다. Table 4의 1 초과 값(1.84 등)은 이 식이라야 나온다. 후보 front가 점 하나면 항을 0으로 둔다(논문 BK40 SPEA2의 0.00과 같은 처리).
  - `src/bakery/paper_ref.py`: 논문 기준값. Table 4와 본문 수치는 정확값이고 Fig. 7a, 10a, 11, 12 값은 300 dpi 그림 판독값이다.
  - `tests/test_metrics.py`: 지표 손계산 테스트 5개. 전체 19개 통과.
- 지표 기준: PF*는 NSGA-II front 전체(seed 10 × snapshot 4)의 nondominated 합집합이다(잠정). RHA와 DPF_norm은 그 front들의 min/max로 [0, 1] 정규화하고 RV = (1.1, 1.1)을 쓴다. DPF는 논문 Fig. 11 축이 분 단위이므로 원 단위 값(DPF_raw)으로 비교한다.
- 실행 점검: infeasible 비율 BK15 0.022%, BK50 0%. front에 오른 해는 모두 checker PASS다. 같은 seed로 두 번 실행해 지표가 같음을 확인했다.

**논문 대조**

| 항목 | BK15 논문 | BK15 재현 | BK50 논문 | BK50 재현 |
|---|---|---|---|---|
| PF* | (471, 93), (478, 84), (480, 72) | (471, 119), (474, 86), (491, 74) | (934, 2590) … (995, 1243), 7개 | (960, 1956) … (1022, 1208), 7개 |
| 최소 makespan | 471 | 471 (seed 7/10) | ≈ 934 | 960 (seed 중앙값 986.5) |
| 최소 OIDT | 72 | 74 (seed 중앙값 95) | 1243 | **1208** (seed 중앙값 1330) |
| E1→E2 | +9 / −21 | +20 / −45 | +61 / −1348 | +62 / −748 |
| 재현 점 중 논문 PF*에 지배되는 점 | – | 2/3 | – | 6/7 |
| RHA 50→300 (NSGA-II) | 67 → 97 | 중앙값 74 → 84, seed 1 59 → 69 | 66 → 97.5 | 중앙값 65 → 88, seed 1 71 → 89 |
| DPF 50→300 (분) | 44 → 11 | 중앙값 22 → 13 | 258 → 78 | 중앙값 283 → 91 |
| PDS 300 (Table 4) | 0.00 | 중앙값 0.33 | −0.09 | 중앙값 0.14 |
| 50 iteration 시간 | 13분 | 약 4초 | 342분 | 약 54초 |

- **맞는 점**: BK15 최소 makespan 471, iteration에 따라 RHA가 오르고 DPF가 내리는 경향, BK50 DPF의 규모(수백 분 → 수십 분), BK50 front 개수(7)와 OIDT 범위(≈1200–2000).
- **다른 점**: BK50 낮은 makespan 쪽(< 960)에 도달하지 못한다. 논문 PF*가 재현 PF*를 대부분 지배한다. E1 부근 OIDT가 논문보다 BK15 +26, BK50은 논문 E1 OIDT 2590보다 오히려 낮지만 makespan이 26분 길다.
- **해석 시 주의**:
  - 논문 PF*는 5종 × iteration 4종의 합집합이고, 재현 PF*는 NSGA-II만의 합집합이다. PDS, MSF, DPF, RHA의 절대값은 비교 대상이 아니다. 5종을 모두 돌린 뒤 다시 계산한다.
  - 논문은 run 하나라서 seed 간 편차가 크다. 논문 값 다수가 재현 seed 분포 안에 든다(BK50 RHA, BK15·BK50 DPF).
  - BK50 최소 OIDT 1208이 논문 E2 1243보다 낮다. 오븐 구획 수 차이(9 vs 10, 4절)와 OIDT 정의 차이가 원인일 수 있다(확인 필요).
  - 계산 시간은 하드웨어와 구현이 달라 비교하지 않는다. 논문의 decoder가 훨씬 느렸던 것으로 보인다.
- 논문 BK50 E1 판독을 940–960에서 **≈ 934**로 고친다. Fig. 10a의 PF* 첫 점이 (934, 2590)이고, 본문의 E1→E2 +61 / −1348과 E2 OIDT 1243이 함께 맞는다(934 + 61 = 995, 1243 + 1348 = 2591). CP-SAT 931(8절)과도 모순이 없다.

## 10. 팀 공유용 현황판 (2026-11-27)

- `status/index.html`: 진행 순서(단계별 진행 막대), 다음 할일, 팀 확인 필요 항목, NSGA-II 논문 대조, 전체 할일을 한 쪽에 모았다. 외부 자원 없이 브라우저로 바로 열린다.
- `status/build-status.py`가 생성한다. 할일 목록은 `docs/TODO.md` (B)(C)의 체크박스를, NSGA-II 수치는 `results/stage2-nsga2/summary.json`을 읽는다. "다음 할일"과 "팀 확인 필요"는 스크립트 안의 목록이라 TODO와 함께 고친다.
