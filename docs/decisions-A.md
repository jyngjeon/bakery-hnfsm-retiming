# TODO (A) 팀 결정 자료 (2026-11-26)

`docs/TODO.md` (A) 6개 항목의 결정 자료다. **2026-11-26 팀이 아래 "권장"을 모두 채택했다.** 확정 내용은 `PROGRESS.md` 5절에 있다. 항목마다 두 기준으로 판단했다.

1. 논문 표현: PDF 원문에 가장 가까운 해석
2. 논문 결과: PF*(Fig. 7, p.9)와 가장 가까운 결과를 내는 선택

비교 기준 값은 다음과 같다.
- BK15: E1 ≈ (471, 93), E2 ≈ (480, 72)
- BK50: E1 makespan ≈ 940–960(그림 판독), E2 OIDT 1243, E1→E2 makespan +61 / OIDT −1348. 따라서 E1 OIDT ≈ 2591, E2 makespan ≈ 1001–1021

## 요약

| # | 항목 | 논문 표현 | 논문 결과 | 권장 | 근거의 강도 |
|---|---|---|---|---|---|
| A1 | OIDT 정의 | M2 | 합집합 | **합집합(주) + M2(병기)** | 강함: M2는 OIDT가 음수가 됨 |
| A2 | infeasible 처리 | constrained-dominance(GDE3 부록) | 영향 없음 | **(1e9, 1e9) 유지 + 발생률 보고** | 실험상 영향 없음(0.02%) |
| A3 | 오븐 tie-break | first-fit | BK15는 used_first, BK50은 first-fit | **first-fit 유지 + used_first는 민감도 실험** | 중간: 인스턴스마다 결론이 다름 |
| A4 | co-baking | 본문 (a) / Fig. 3 (b) | (a) | **(a) 겹침 자유** | 중간: (b)는 BK50에서 논문 값보다 나빠짐 |
| A5 | batch 전개 | 언급 없음 | **전개** | **전개 + Group 18 2회** | 전개는 강함, Group 18은 결과로 판별 불가 |
| A6 | iteration / HV | 세대 수 | 세대 수 | **세대 수, RHA 주 지표** | 강함(iteration) / 관례(RV) |

## 실험

| 실험 | 스크립트 | 결과 |
|---|---|---|
| CP-SAT min makespan, 변형별 | `experiments/a-decisions-cpsat.py` | `results/a-decisions-cpsat/summary-{bk15,bk50}.json` |
| NSGA-II(Table 5), 변형별 | `experiments/a-decisions-nsga2.py` | `results/a-decisions-nsga2/summary-*.json`, `fronts-*.csv` |

NSGA-II 설정:
- Table 5(p.20)에 맞춰 population 50, SBX rate 1, polynomial mutation 1/NG, binary tournament
- distribution index는 Table 5에 없어 jMetalPy 기본값 20을 썼다.
- 15,000회 평가(300세대)
- seed: BK15 1–10, BK50 1–3
- 실험 범위 밖의 설정은 현행(합집합, first-fit, 겹침 자유, 전개, 1e9 penalty)으로 고정하고 한 요인씩 바꿨다.
- front에 오른 해는 모두 checker PASS다.

decoder 옵션은 `hnfsm_decode(..., oven_rule, cobake, oidt)`다. 기본값이 현행 동작이고, 회귀 테스트로 확인했다.

### 결과 1. BK15 NSGA-II, seed 10개를 합친 front

| 변형 | OIDT (ms ≤ 471) | OIDT (ms ≤ 480) | seed별 OIDT(ms ≤ 480) 중앙값 | base 대비 p (Mann–Whitney) |
|---|---|---|---|---|
| **논문 PF*** | **93** | **72** | – | – |
| base | 119 | 86 | 105.5 | – |
| A1 M2를 최적화 | 33 | 12 | 26 (최저 **−28**) | 0.0002 |
| A3 used_first | 107 | 78 | 88 | **0.004** |
| A3 min_idle | 97 | 85 | 91 | 0.028 |
| A4 same_start / same_start_end | 121 | 93 | 112 | 0.50 |
| A5 no_batch | 105 | 86 | 109 | 0.76 |
| A3 uf + A4 sse | 108 | 82 | 96.5 | 0.47 |
| A3 uf + A5 nb | **93** | 83 | 97 | 0.27 |
| A3 uf + A4 sse + A5 nb | 108 | 86 | 98 | 0.36 |

- 모든 변형의 최소 makespan은 471이다.
- same_start와 same_start_end는 BK15에서 결과가 같다.

### 결과 2. BK50 NSGA-II, seed 3개를 합친 front

| 변형 | 최소 makespan | 최소 OIDT | 비고 |
|---|---|---|---|
| **논문 PF*** | **≈ 940–960** | **1243** | – |
| base | 985 | **1243** | 최소 OIDT가 논문 E2와 같음 |
| A1 M2를 최적화 | 987 | 108 | 논문보다 한 자릿수 작음 |
| A3 used_first | 965 | 962 | 논문 E2보다 낮음 |
| A3 min_idle | 949 | 1145 | |
| A4 same_start_end | 1010 | 1540 | 논문보다 나쁨 |
| A5 no_batch | **638** | 386 | 논문과 규모가 다름 |
| A5 g18_once | 975 | 1125 | base와 비슷 |

### 결과 3. CP-SAT min makespan

| 인스턴스 | 변형 | makespan | 상태 / 하한 |
|---|---|---|---|
| BK15 | 전개, 겹침 자유(현행) | 471 | OPTIMAL |
| BK15 | same_start / same_start_end | 471 / 471 | OPTIMAL |
| BK15 | no_batch | 471 | OPTIMAL |
| BK50 | 전개(현행) | 931 | FEASIBLE(600초) / 547 |
| BK50 | g18_once | 969 | FEASIBLE(600초) / 540 |
| BK50 | no_batch | **569** | FEASIBLE(600초) / 423 |

## 항목별 판단

### A1. OIDT 정의
- **논문 표현**: 식은 M2(p.5) 하나다. p.4에서는 "running an oven while it is only partially occupied causes energy waste"라고 쓰고, OIDT를 "total idle time of all oven compartments"(p.4)로 설명한다. 둘 다 오븐이 비어 있는 시간을 뜻한다.
- **논문 결과**: M2를 그대로 최적화하면 BK15에서 OIDT가 **−28**까지 내려간다. 같은 그룹이 겹쳐 구울 때 PT를 두 번 빼기 때문이다(`tests/test_decoder.py::test_oidt_m2_double_subtracts_overlap`). idle time이 음수일 수는 없다. 값도 논문 PF*보다 BK15에서 60, BK50에서 1100 이상 낮다. 합집합은 BK15에서 논문보다 약간 높고(86 vs 72), BK50 최소 OIDT는 1243으로 논문 E2와 같다.
- **권장**: 합집합을 주 목적함수로 쓰고, 보고서에서는 "M2의 의도(비어 있는 시간)를 따르되 같이 굽는 경우를 한 번만 차감하도록 해석했다"고 쓴다. M2 값은 근거 표로 병기한다.
- **팀이 정할 것**: 이 해석으로 확정할지 여부

### A2. infeasible 순서 처리
- **논문 표현**: HNFSM의 infeasible 처리는 서술이 없다. 부록 GDE3(p.17, Eq. A6)에만 constraint domination이 나온다.
- **논문 결과**: NSGA-II 실행 중 infeasible 비율은 BK15 0.02%, BK50 0%다. random 순서에서는 3.4%였지만 탐색이 금방 feasible 영역으로 들어간다. 따라서 어떤 처리를 고르든 front는 사실상 같다.
- **구현 비용**: jMetalPy 1.9의 기본 comparator는 `DominanceComparator`이고 constraint를 무시한다. (d)를 쓰려면 다음이 필요하다.
  1. `number_of_constraints`와 위반량(예: 근무시간을 넘긴 분)을 정의한다. decoder가 배치에 실패한 그룹의 위반량을 계산하도록 고쳐야 한다.
  2. NSGA-II·SPEA2·GDE3에 `DominanceWithConstraintsComparator`를 넘긴다.
  3. OMOPSO·SMPSO는 따로 확인한다.
- **권장**: 재현에서는 (a) 현행 `(1e9, 1e9)`를 유지하고 알고리즘별 infeasible 발생률을 보고한다. PSO 계열에서 발생률이 크게 나오면 그때 (d)로 바꾼다.
- **팀이 정할 것**: 이 방식으로 갈지, 처음부터 (d)를 구현할지

### A3. 오븐 tie-break
- **논문 표현**: "selected based on availability"(p.4)라고만 쓴다. first-fit이 가장 단순한 해석이다.
- **논문 결과**: 인스턴스마다 다르다.
  - BK15: used_first가 OIDT를 유의하게 낮춰(p = 0.004) 논문 E2(72)에 더 가깝다(78).
  - BK50: first-fit의 최소 OIDT가 논문 E2와 정확히 같다(1243). used_first는 962로 논문보다 낮아진다.
  - 어느 쪽도 두 인스턴스를 동시에 더 잘 맞추지 못한다.
- **권장**: first-fit을 유지한다. 근거는 표현이 가장 가깝고, BK50 E2와 일치하고, 이미 검증된 기본값이라는 점이다. used_first와 min_idle은 "가정 민감도" 실험으로 보고한다. B0와 P1(Retiming)은 같은 규칙을 쓴다.
- **팀이 정할 것**: 이 방침으로 확정할지 여부

### A4. 같은 그룹 co-baking
- **논문 표현**: 본문(p.4 "ovens can operate multiple products from the same product group at a time", p.6 M12 설명)에는 동시 시작 조건이 없다. Fig. 3(p.4)만 시작·종료가 같은 형태다.
- **논문 결과**:
  - BK15: makespan(471)과 OIDT 모두 차이가 유의하지 않다.
  - BK50: same_start_end에서 front가 (1010, 1540)으로 나빠져 논문 E2(1243)에 못 미친다. 논문이 이 제약을 썼다면 같은 예산에서 1243을 얻기 어렵다(seed 3개라 약한 근거).
- **권장**: (a) 겹침 자유를 유지한다.
- **팀이 정할 것**: 이 방침으로 확정할지 여부

### A5. batch 전개와 Group 18
- **batch 전개**:
  - **논문 결과**: BK50에서 전개하지 않으면 NSGA-II 최소 makespan이 638(CP-SAT 569)이다. 논문 E1(≈ 940–960)보다 300분 이상 짧아 규모부터 다르다. 전개하면 985(NSGA-II), 931(CP-SAT)로 논문과 같은 범위다.
  - BK15는 전개 여부가 makespan에 영향을 주지 않아 판별할 수 없다(둘 다 471).
  - **권장**: 전개한다(현행). 근거가 강하다.
- **Group 18 Dough C**:
  - 1회와 2회의 결과 차이가 seed와 탐색 잡음 범위 안이다(NSGA-II 975 vs 985, CP-SAT는 시간 제한 내 해 969 vs 931). 결과로는 판별할 수 없다.
  - 해석상 근거는 두 가지다.
    - 2회(현행): 데이터셋 Description 시트에 "batches of same group do not depend on each other"라고 되어 있다. 2회차 Bread가 독립 batch가 되려면 자기 Dough가 필요하다.
    - 1회: 원본 Excel의 Dough C 행이 batches=1이다.
  - **권장**: 2회(현행). 독립 batch라는 데이터 설명과 그룹 구조(파생 제품이 기준 제품에 WT로 묶임)를 유지할 수 있다.
- **팀이 정할 것**: Group 18을 2회로 확정할지 여부

### A6. iteration과 HV reference point
- **iteration**: 세대 수로 확정하기를 권장한다.
  - 부록의 알고리즘 설명이 모두 세대 G = {1, …, G_max} 단위다(p.17–20).
  - 계산시간 근거(p.14): "50 iterations"에 NSGA-II가 BK15 13분, BK50 342분 걸렸다. 평가 횟수로 해석하면 50회 평가는 population 50의 초기화뿐이고, 1회 평가에 약 7분이 걸린다는 뜻이 된다.
  - 구현에서는 300세대를 15,000회 평가(초기 50 + 세대마다 50)로 두고, 50·100·200세대 시점의 front를 저장한다.
- **HV**:
  - 논문은 HV 자체보다 RHA = HV_PF / HV_PF*(p.13, Eq. 6)로 비교하며, RV 값은 주지 않는다.
  - 권장: RHA를 주 지표로 쓴다. PF*는 같은 인스턴스에서 모든 알고리즘·iteration의 해를 합친 nondominated set으로 둔다. RV는 그 집합의 nadir를 기준으로 [0, 1] 정규화한 뒤 (1.1, 1.1)로 둔다.
  - 논문의 RHA 수치와 직접 맞추는 것은 RV가 달라 불가능하다. 순위와 경향만 비교한다.
- **팀이 정할 것**: RV 규칙

## 해석상 주의
- 논문 PF*는 5개 알고리즘 × iteration 4종(1 run씩)을 합친 것이다. 이번 실험은 NSGA-II 하나에 seed 10개 또는 3개이므로 예산과 구성이 다르다.
- BK50은 seed가 3개뿐이다. A3·A4의 BK50 결과는 경향으로만 읽는다.
- BK50 오븐 구획은 공개 데이터에서 9개다(논문 10개, `paper-conformance.md` #23). BK50 값이 정확히 일치하기는 어렵다.
