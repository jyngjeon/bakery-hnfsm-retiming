# 원논문 대비 구현 적합성 검토

- **기준 문서**: `paper/s41598-022-26866-9.pdf`. 쪽수는 PDF 페이지 번호다.
- **검토 대상**: 원본 노트북 `1단계.ipynb`(전처리 cell 4·6, CP-SAT cell 8, HNFSM decoder cell 13, NSGA-II cell 23)와 `checker.py`.
- **리팩토링 후 위치 (2026-11-24)**: 아래 표의 cell 번호와 checker 행 번호는 원본 기준이다. 현재 코드는 cell 4·6 → `src/bakery/preprocess.py`, cell 8 → `src/bakery/cpsat.py`, cell 13 → `src/bakery/decoder.py`, cell 23 → `src/bakery/problem.py` + `experiments/stage1-nsga2-demo.py`, `checker.py` → `src/bakery/checker.py`에 있다. 로직은 같고 결과도 같다(PROGRESS.md 7절). 다른 점은 #11 UNLIMITED 버그 수정뿐이다.
- **방법**: 원본은 수정하지 않았다. 검증은 decoder와 checker 복사본을 별도로 실행해 수행했다(2026-11-24).
- **미실행**: CP-SAT 변형 실행(batch 미전개 비교, BK50)은 하지 않았다.

판정 기호: **MATCH** 일치 / **DEVIATION** 차이 / **NOT IMPL** 미구현 / **AMBIGUOUS** 논문이 명확하지 않음

## 1. 적합성 표

| # | 논문 (위치) | 구현 위치 | 판정 | 영향 / 권장 |
|---|---|---|---|---|
| 1 | Makespan = max CT_{g,p,s} (M1, p.5) | decoder `makespan`(cell 13), CP-SAT `AddMaxEquality`(cell 8), checker 283행 | MATCH | – |
| 2 | OIDT = Σ_{k∈V}(end_k − start_k − Σ_g Σ_p PT_{g,p,k}) (M2, p.5). "OIDT may exceed the makespan since it calculates the total idle time of all oven compartments" (p.4) | 구획별 점유구간 **합집합** 기준(cell 13 끝, checker 244–260행) | DEVIATION (의도된 차이, 제안서 5.3) | 원래 순서 기준 BK15 273 vs 187, BK50 2409 vs 1362. 두 정의를 모두 보고(3a) |
| 3 | Min makespan, Min OIDT (M3, M4, p.6) | jMetalPy 2목적(cell 23). CP-SAT는 makespan만 | MATCH | – |
| 4 | ST_{g,1,1} ≥ 0 (M5) | `T_g`를 0부터 탐색, CP-SAT 변수 하한 0 | MATCH | – |
| 5 | ST_{g,p,1} = ST_{g,1,1} + WT_{g,p} (M6). Table 2: "WT_{g,p} time difference between product p and its predecessor" | WT를 s=1에만 적용(cell 4·6·13, checker 186–194행) | MATCH | Table 1에서 Product B WT 36 = 9+18+9 |
| 6 | PT > 0 (M7) | assert(cell 4·6), checker 138행 | MATCH | – |
| 7 | CT = ST + PT, ST_{s+1} = CT_s (M8, M9, p.6) | 상대 오프셋 고정(cell 13 `rel_s/rel_e`), checker 197–205행 | MATCH | – |
| 8 | Σ_k O_{g,p,s,k} ≤ 1 (M10); "selected based on availability" (p.4) | 적격 기계 중 first-fit 1대 | 제약은 MATCH, 선택 규칙은 AMBIGUOUS | 3b |
| 9 | 단일 설비 k ∈ M∖(U∪V) (M11) | bitmask 비중복(반열린 구간), 같은 그룹 내부도 `loc_m`으로 금지. CP-SAT NoOverlap | MATCH | 연속 사용 허용은 표준적 해석 |
| 10 | Σ O ≤ n(CT−ST), k∈V (M12). "Constraint (M12) allows ovens to bake multiple products from the same group" (p.6). "ovens can operate multiple products from the same product group at a time (Fig. 3)" (p.4) | 다른 그룹 간 겹침 금지, 같은 그룹은 겹침 형태 제한 없음(cell 13 OVEN 분기, cell 8, checker 229–242행) | 본문과는 MATCH, 식은 AMBIGUOUS | 3c |
| 11 | 무제한 용량 k∈U (M13). 휴지·냉각·발효는 blocking 없음(p.4) | 빈 자원 → NONE. Proving chamber는 UNLIMITED로 분류되었지만 참조하는 작업이 없음 | 실질 MATCH | 원본의 잠재 버그(decoder KeyError, CP-SAT NoOverlap 적용)는 리팩토링 때 수정함 |
| 12 | start_l < end_l (M14) | assert(cell 4·6) | MATCH | – |
| 13 | 작업당 작업자 ≤1, 작업자 동시작업 금지 (M15, M16) | first-fit 작업자 배정, bitmask와 `loc_e`, CP-SAT NoOverlap, checker 267–278행 | MATCH, 선택 규칙 AMBIGUOUS | – |
| 14 | ST ≥ start_l, CT ≤ end_l (M17, M18) | 근무 외 시간 비트 차단, `group_max_tg`, CP-SAT `OnlyEnforceIf`, checker 173행 | MATCH | infeasible 처리는 논문에 없음(3d) |
| 15 | 기계 또는 작업자 또는 둘 다 없음 (M19) | `resource_type` 4종, checker 144–170행 | MATCH | – |
| 16 | t: "Index of production runtime in minutes" (Table 2, p.5) | 1분 단위 | MATCH / AMBIGUOUS | 3g |
| 17 | "products that are placed first in the order will get priority in occupying the machines and employees. The following products are scheduled according to machine availability" (p.4) | 그룹 순서대로 가장 이른 실행가능 `T_g`에 배치하고, 앞 그룹 배정은 고정 | MATCH (가장 자연스러운 해석) | – |
| 18 | SPV: 값이 작은 순서로 인덱스 정렬 (p.8, Table 3) | `np.argsort(kind="mergesort")` | MATCH | [1.22, −1.08, 1.90] → {2,1,3} 재현 |
| 19 | 벡터 길이 = 제품 그룹 수 (p.8) | 16(BK15), 62(BK50), batch 전개 후 | AMBIGUOUS | 논문에 batch 언급 없음(3e) |
| 20 | Table 5 (p.20): population 50, SBX rate 1, polynomial mutation 1/NG, binary tournament. GDE3 CR=1, F=0.4. OMOPSO/SMPSO 계수 | cell 23: population 20, SBX 0.9, 평가 200회, seed 없음 | DEVIATION (데모) | Table 5로 맞추고 seed 고정. 나머지 4종 미연결 |
| 21 | 예산: iteration 50/100/200/300, 인스턴스·알고리즘별 1 run (pp.10–14) | 없음 | NOT IMPL | iteration 정의 결정 필요(TODO A6) |
| 22 | 지표: PDS (Eq. 2), MSF (Eq. 3), DPF (Eq. 4), HV/RHA (Eq. 5–6, reference vector RV), PCA + GMM (p.13) | 없음 | NOT IMPL | RV 값은 논문에 없음 |
| 23 | BK15: "three employees, eight machines, and two ovens with four compartments". BK50: "ten employees, fourteen machines, and three ovens, and ten compartments" (p.3) | BK15: 작업자 3, 비오븐 6 + 오븐 2 = 8, 구획 4. BK50: 작업자 10, 비오븐 14, 오븐 3종, **구획 9** | BK50 구획 수만 DEVIATION | 공개 데이터에서 Oven 7(id 20) 누락. 수정 불가, 문서화 |
| 24 | "BK15 has only 3 groups with more than one product" (p.9) | 정제 BK15: 15그룹, 21제품, 다제품 그룹 3개 | MATCH | BK15의 "15"는 그룹 수로 보는 것이 맞다 |
| 25 | Table 1 예제 (p.4), Fig. 2 Gantt (p.3) | 재현(3h), `tests/test_decoder.py::test_paper_table1_worked_example` | MATCH | – |
| 26 | PF* (Fig. 7, p.9): BK15 E1≈(471, 93), E2≈(480, 72), "9 min … 21 min". BK50 E2 OIDT 1243, E1→E2 +61 / −1348 | CP-SAT BK15 최소 471, decoder 최선 474–475, BK50 random 최선 1057 | 부분 일치 | BK15 makespan 하한은 논문과 일치. BK50은 최적화 후 비교 필요 |

## 2. 쟁점별 판단 (3a–3i)

### 3a. OIDT 정의
- 논문의 유일한 정의는 M2(p.5)다. Table 2(p.5)는 `start_k`/`end_k`를 "first/last operation" 시각으로, `PT_{g,p,k}`를 "processing time of product p in group g processed by machine k"로 정의한다.
- 같은 그룹 제품이 한 구획에서 겹쳐 구워질 때 M2는 PT를 두 번 차감한다. 논문은 이를 다루지 않는다.
- 재계산 결과:

  | | 합집합 | M2 그대로 | 논문 PF* 최소 OIDT |
  |---|---|---|---|
  | BK15 원래 순서 | 273 | 187 | – |
  | BK50 원래 순서 | 2409 | 1362 | – |
  | BK15 random 3000회 최소 | 105 | **19** | 72 |
  | BK50 random 300회 최소 | 2106 | **1054** | 1243 |

  같은 구획에서 겹치는 쌍은 원래 순서 기준 BK15 3쌍, BK50 33쌍이다.
- **판단**: M2를 그대로 쓰면 random search만으로도 논문의 최선값보다 낮아지므로, 논문이 이 방식을 썼다고 보기 어렵다. 합집합 해석이 더 그럴듯하다. 그러나 논문이 명확하지 않으므로 팀 결정 사항이다(TODO A1). 권장은 합집합을 주 지표로 쓰고 M2를 함께 보고하는 것이다.

### 3b. 자원 선택 규칙
- 논문은 "one should be selected based on availability"(p.4)와 앞선 제품의 우선 점유(p.4)만 말한다. 동률을 깨는 규칙은 없다.
- 코드는 first-fit(최저 인덱스)이다. 그 결과 BK50에서 Oven 1과 Oven 4에 부하가 몰리고 OIDT가 커질 수 있다.
- 선택지: first-fit 유지 / 이미 사용 중인 구획 우선 / 최소 부하. TODO A3.

### 3c. 같은 그룹 co-baking
- 본문(p.4, p.6)은 같은 그룹만 허용한다고 쓰고, Fig. 3(p.4)은 같은 시작·종료로 함께 굽는 그림이다.
- 식 M12는 용량 n만 제한하고 그룹 조건이 없다. 온도나 동시 시작 조건은 논문 어디에도 없다.
- 코드는 같은 그룹이면 어떤 겹침도 허용한다. 그룹당 제품 수 ≤ n이고 제품당 베이킹은 1회이므로 용량 n은 자동으로 만족된다.
- 본문과는 일치한다. "동시 시작만 허용"할지는 TODO A4.

### 3d. 근무시간과 infeasibility
- 논문은 M14, M17, M18만 제시한다. infeasible 해의 penalty, repair, 처리 방식에 대한 서술이 없다(본문 검색으로 확인).
- 코드는 배치에 실패하면 `(1e9, 1e9)`를 반환한다. BK15 random 순서의 3.4%(102/3000)가 여기에 해당하고, BK50은 0/300이다. TODO A2.

### 3e. 인스턴스 규모 비교

| | 그룹 | 제품 | 작업 | batch 전개 후 | 비오븐 기계 | 오븐 / 구획 | 작업자 |
|---|---|---|---|---|---|---|---|
| 정제 BK15 | 15 | 21 | 159 | 16그룹 / 164작업 | 6 | 2종 / 4 | 3 |
| 논문 BK15 (p.3) | – | "15 products" | – | 언급 없음 | 8 machines(오븐 포함으로 해석) | 2 / 4 | 3 |
| 정제 BK50 | 40 | 77 (76 + G31 분리) | 448 | 62그룹 / 679작업 | 14 | 3종 / **9** | 10 |
| 논문 BK50 (p.3) | – | "approximate" 50 | – | 언급 없음 | 14 | 3 / **10** | 10 |

- batch 의미는 데이터셋 Description 시트에 근거한다: "batches of same group do not depend on each other".
- BK15 CP-SAT 최소 makespan 471이 논문 E1(≈471)과 일치한다. batch 전개가 논문과 같다는 약한 근거다. 전개하지 않은 경우의 비교는 미실행이다(확인 필요).

### 3f. WT와 no-wait
- WT는 그룹 기준 제품 시작 대비 각 제품 첫 작업의 시차다(M6, Table 2).
- no-wait는 M9다.
- WT가 (g,p) 인덱스만 가지므로, s≥2의 WT를 0으로 정규화한 것은 논문과 모순되지 않는다.

### 3g. `T_g` 탐색 방식
- 논문은 "scheduled according to machine availability"(p.4)와 분 단위 시간(Table 2)만 제시한다.
- 1분 단위로 가장 이른 시작시각을 찾는 방식은 충실한 해석이다.
- event 기반 탐색이면 더 빠르겠지만, BK50 1회 약 21 ms라 필요하지 않다.

### 3h. Table 1 예제 재현
- 인스턴스: 1그룹, Kneader 1대, Oven 1대, 작업자 1명. Dough rest, Proofing, Cooling은 NONE이다.
- 결과: A Baking 61–103, B Baking 156–201. **makespan 244**로 Fig. 2 축의 240 직후와 일치한다. **oven idle 53**은 두 정의 모두 같고 Fig. 2의 Δ와 일치한다. checker도 PASS.
- Fig. 3은 수치가 없어 재현할 수 없다.

### 3i. Table 5와 예산
- 1절 표 20·21행 참고.
- OMOPSO(uniform + non-uniform mutation, C1·C2 ~ U(1.5, 2), W ~ U(0.1, 0.5))와 SMPSO(C1·C2 ~ U(1, 2.5), W = 0.2)는 jMetalPy에서 명시적으로 설정해야 한다.

## 3. 새로 발견한 문제

1. **UNLIMITED 기계**: decoder `mach_mask`는 SINGLE 기계만 가진다(KeyError 위험). CP-SAT은 MACHINE이면 UNLIMITED에도 NoOverlap을 건다. 현재 데이터에서는 영향이 없다. **→ 2026-11-24 리팩토링 때 수정함.**
2. **BK50 Group 31 2회차 Boxing 자원 공백**: NONE으로 처리되었다. 1회차는 Manual이다.
3. **그룹 내부 배정 순서**: (p, s) 순서로 배정하므로 다른 배정이면 가능한 시각을 놓칠 수 있다. 실행가능성에는 영향이 없고 `T_g` 지연 가능성만 있다. 영향은 작다.
4. **cell 14 markdown**: 471을 논문 본문 수치처럼 인용했다. 실제 출처는 CP-SAT 결과와 Fig. 7a 판독이다.
