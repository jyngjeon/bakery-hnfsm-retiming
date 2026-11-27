# TODO (2026-11-28 기준)

## (A) 팀 결정 필요 (2026-11-26 전 항목 결정)

이 항목들은 임의로 정하지 않는다. 결정이 나면 `PROGRESS.md` "모델링 가정"에 반영한다.

**결정 자료: [`decisions-A.md`](decisions-A.md)** (2026-11-26). 팀이 권장안을 모두 채택했다. 각 항목의 "결정" 줄이 확정안이다. CP-SAT와 NSGA-II(Table 5)로 변형별 결과를 논문 PF*와 비교했다. 아래 "실험" 줄은 그 요약이다.

- [x] **A1. OIDT 정의**
  - **결정(2026-11-26): (a) 합집합을 주 목적함수로 쓰고, M2 그대로의 값을 병기한다.**
  - 선택지: (a) 구획별 점유구간 합집합(현재 코드), (b) 논문 M2 그대로(end−start−ΣPT, 동시 베이킹 PT 이중 차감)
  - 근거: random search만으로도 M2 값이 논문 PF* 최소 OIDT보다 낮아진다(BK15 19 < 72, BK50 1054 < 1243). 합집합은 논문 값보다 높게 머문다.
  - 권장: (a)를 주 목적함수로 쓰고 (b)를 민감도 지표로 함께 보고한다.
  - 실험: M2를 최적화하면 BK15 OIDT가 −28까지 내려간다(음수 idle). BK50 합집합 최소 OIDT는 1243으로 논문 E2와 같다.
- [x] **A2. infeasible 순서 처리**
  - **결정(2026-11-26): (a) `(1e9, 1e9)`를 유지하고, 알고리즘별 infeasible 발생률을 보고한다. PSO 계열에서 발생률이 크면 다시 논의한다.**
  - 현재: `(1e9, 1e9)`. BK15 random 순서의 3.4%가 해당된다.
  - 선택지: (a) 현행 유지, (b) 근무시간 초과량에 비례하는 penalty, (c) repair(배치 실패 그룹을 앞으로 당겨 재시도 등), (d) constrained-dominance
  - 권장(갱신): 재현에서는 (a)를 유지하고 발생률을 보고한다. PSO 계열에서 발생률이 크면 (d)로 바꾼다.
  - 실험: NSGA-II 실행 중 infeasible 비율은 BK15 0.02%, BK50 0%라 front에 영향이 없다. jMetalPy 기본 comparator는 constraint를 무시하므로, (d)를 쓰려면 위반량 정의와 comparator 지정이 필요하다.
- [x] **A3. 자원 tie-break 규칙**, 특히 오븐
  - **결정(2026-11-26): (a) first-fit을 유지한다. used_first(와 min_idle)는 가정 민감도 실험으로 보고한다. B0·P1은 같은 규칙을 쓴다.**
  - 선택지: (a) first-fit 최저 인덱스(현재), (b) 이미 사용 중인 구획 우선(OIDT 감소), (c) 가장 일찍 비는 자원 / 최소 부하
  - 권장: 재현에는 (a)를 유지하고 문서화한다. (b)는 민감도 실험으로 돌린다. Retiming 비교와 섞이지 않게 B0·P1은 같은 규칙을 쓴다.
  - 실험: BK15에서는 used_first가 OIDT를 유의하게 낮춘다(ms ≤ 480에서 78 vs 86, 논문 72, p = 0.004). BK50에서는 first-fit 최소 OIDT가 논문 E2와 같고(1243), used_first는 962로 논문보다 낮아진다. 두 인스턴스를 동시에 더 잘 맞추는 규칙은 없다.
- [x] **A4. 같은 그룹 co-baking 규칙**
  - **결정(2026-11-26): (a) 같은 그룹이면 겹침 형태에 제한을 두지 않는다.**
  - 선택지: (a) 같은 그룹이면 어떤 겹침도 허용(현재), (b) 같은 구획에서는 ST·CT가 같을 때만 허용(Fig. 3 형태)
  - 권장: (a) 유지. 논문 본문(p.4, p.6)에 동시 시작 조건이 없다.
  - 실험: BK15에서는 CP-SAT 471이 그대로이고 OIDT 차이도 유의하지 않다(p = 0.50). BK50에서는 (b) front가 (1010, 1540)으로 논문 E2(1243)보다 나쁘다(seed 3개).
- [x] **A5. batch 전개와 Group 18**
  - **결정(2026-11-26): (a) batch를 독립 그룹으로 전개하고, Group 18 Dough C는 (i) 2회 전개한다.**
  - 선택지: (a) batch를 독립 그룹으로 전개(현재), (b) 전개하지 않음
  - Group 18 Dough C: (i) 2회 전개(현재), (ii) 1회만
  - 권장: (a)와 (i). BK15 CP-SAT 471이 논문 E1(≈471)과 일치한다.
  - 실험: BK15는 전개하지 않아도 471이라 판별할 수 없다. BK50은 전개하지 않으면 makespan 638(NSGA-II), 569(CP-SAT)로 논문 E1 ≈ 940–960과 규모가 다르다. 따라서 (a)를 강하게 지지한다. Group 18 (i)·(ii)는 결과 차이가 잡음 범위라 판별할 수 없다.
- [x] **A6. "iteration"의 의미와 HV reference point**
  - **결정(2026-11-26): iteration은 (a) 세대 수다(population 50 × 300세대 = 15,000회 평가). 주 지표는 RHA(p.13, Eq. 6)다. PF*는 모든 알고리즘의 해를 합친 nondominated set이고, RV는 [0, 1] 정규화 후 (1.1, 1.1)이다.**
  - 논문은 iteration 50/100/200/300의 정의를 밝히지 않는다. 선택지: (a) 세대 수(×population 50 = 최대 15,000 평가), (b) 평가 횟수
  - 권장: (a). 제안서의 "같은 평가 횟수 15,000회"와도 맞는다.
  - HV reference point는 논문에 값이 없다. 권장: B0·P1의 해를 합쳐 정규화한 뒤 (1.1, 1.1)을 쓴다(확인 필요).
  - 근거 보강: p.14에서 "50 iterations"에 NSGA-II가 BK15 13분, BK50 342분 걸렸다. 평가 횟수로 해석하면 50회 평가는 초기 population 50뿐이므로 성립하지 않는다. 부록 알고리즘도 세대 G 단위다(p.17–20). 재현 실험 A는 논문처럼 RHA(p.13, Eq. 6)를 주 지표로 쓰고, PF*는 모든 알고리즘의 해를 합쳐 만든다.

## (B) Stage 2 전 필수 수정

- [x] **B1.** decoder와 CP-SAT의 UNLIMITED 기계 처리를 고친다. (2026-11-24 리팩토링 때 수정, `tests/test_decoder.py`)
- [ ] **B2.** BK50 Group 31의 2회차 Boxing 자원 공백을 처리한다(Manual로 보정할지 팀 확인).
- [x] **B3.** 알고리즘 설정을 Table 5에 맞추고(population 50, SBX rate 1, polynomial mutation 1/NG, binary tournament) seed를 고정한다. 실행 설정을 기록한다.
  - 2026-11-27: NSGA-II는 `experiments/stage2-nsga2.py`로 해소(seed 1–10, `random`·`numpy.random` 고정, CONFIG를 `summary.json`에 저장). 나머지 4종도 같은 형식으로 연결한다.
- [x] **B4.** 원본 노트북 cell 14의 "논문 BK15 PF* 최소 makespan 약 471분" 표현. 노트북을 삭제해 해소. 보고서에는 출처를 CP-SAT 결과와 Fig. 7a 판독으로 적는다.
- [ ] **B5.** 모델링 가정(PROGRESS.md 5절)을 보고서용 문서로 확정한다. 대상은 OIDT 정의, batch, tie-break, co-baking, infeasible 처리다.
  - 2026-11-26: 내용은 팀 결정으로 확정했다(PROGRESS.md 5절, `decisions-A.md`). 보고서 문안 작성이 남았다.

## (C) 남은 작업 (2026-11-27 계획 변경)

**계획 변경(2026-11-27)**: 제안서 일정은 알고리즘 5종을 먼저 모두 연결하는 순서였다. NSGA-II가 기준 알고리즘이고 B0 vs P1도 NSGA-II만 쓰므로, 순서를 다음처럼 바꾼다.
1. NSGA-II로 구현과 검증을 끝낸다.
2. Retiming을 구현하고 검증한다.
3. B0 vs P1 비교까지 마친다.
4. 그 다음에 나머지 알고리즘 4종(SPEA2 → OMOPSO → GDE3 → SMPSO)을 연결해 재현 실험 A에 덧붙인다.

**1. NSGA-II 구현·검증 마무리**
- [x] 논문 Table 1 손계산 예제를 대조한다. makespan 244, oven idle 53 (`tests/data/paper-table1-example.json`, `tests/test_decoder.py`)
- [ ] Gantt chart를 시각화하고 oven idle 구간과 OIDT 값을 대조한다.
- [ ] makespan 하한과 baseline을 점검한다. random search보다 좋은지 확인한다.
- [ ] R0: random search와 원래 순서를 비교한다.
- [x] NSGA-II를 Table 5 설정으로 정식 연결한다. (2026-11-27, `experiments/stage2-nsga2.py`)
- [x] NSGA-II R1·R2: BK15·BK50 × seed 10개, 300세대까지 실행하고 50·100·200·300세대 front 저장. R1은 seed 1 snapshot (2026-11-27, `results/stage2-nsga2/`)
- [x] 지표 PDS·MSF·DPF·HV/RHA 구현 (2026-11-27, `src/bakery/metrics.py`, `tests/test_metrics.py`)
- [x] NSGA-II 단독으로 논문 PF*·Table 4·Fig. 10–12와 대조한다. (2026-11-27, `notebooks/stage2-nsga2.ipynb`, PROGRESS.md 9절. 논문 그림 판독값은 `src/bakery/paper_ref.py`)
- [ ] BK50 최소 OIDT 1208이 논문 E2 1243보다 낮은 원인을 확인한다(오븐 구획 9 vs 10, OIDT 정의). 해당 스케줄을 Gantt로 본다.

**2. Retiming**
- [x] 명세(`proposal/proposal-idea-01-event-point-retiming.md`)대로 한 그룹 Event-Point Retiming을 구현한다. (2026-11-28: BK15·BK50 공통 최종 모듈, 성능 최적화·API 보완 완료)
- [x] 부분문제 검증: 소형 예제를 전수탐색해 비교한다. (266개 전체·두 정책, 17,712개 부분문제, 불일치 0건; pytest 68개 통과)
- [x] 제안서의 BK15 예비 검증(66개 중 54개 개선) 코드와 자료 위치를 확인한다. (원본 ZIP 확보·체크섬 고정·66개 재현; 별도 공유 경로는 `retiming.md`, `repro/retiming-evidence.json`)

- [x] 최신 main과 Retiming의 호환성을 확인한다. (2026-11-28: `1ec9e45` 병합, pytest 78개, BK15·BK50 기본 모델 API 각 4개 정책 조합 PASS. 소스 수정·NSGA-II 통합 없음)

**3. 개선안 비교 (B0 vs P1)**
- [ ] NSGA-II와 최종 Retiming API를 통합하고 수정된 실제 스케줄·목적값을 함께 보존한다.
- [ ] B0 vs P1: 같은 평가 횟수(15,000)와 같은 실행 시간 두 기준, seed 10개, Wilcoxon
- [ ] 통합 후 B0·P1의 통계적 성능을 검증한다. Retiming 자체의 시간 감소를 Pareto front·HV 향상으로 해석하지 않는다.
- [ ] Ablation(BK15): 자원 순서 변경 허용/고정, 경계 그룹만/전체 그룹

**4. 나머지 알고리즘과 재현 실험 A 완성**
- [ ] SPEA2를 연결한다.
- [ ] OMOPSO를 연결한다(uniform + non-uniform mutation, Table 5 계수).
- [ ] GDE3를 연결한다(CR=1, F=0.4).
- [ ] SMPSO를 연결한다(Table 5 계수).
- [ ] 4종 R1·R2: `experiments/stage2-nsga2.py`와 같은 seed·snapshot·출력 형식
- [ ] 5종 합집합으로 PF*를 다시 만들고 PDS·MSF·DPF·RHA를 재계산한다. 현재 PF*는 NSGA-II만으로 만든 잠정값이다.
- [ ] PCA + GMM cluster
- [ ] 통계 검정: Kruskal–Wallis, Wilcoxon, Holm
- [ ] 논문과 경향을 비교한다(E1≠E2, front 모양, BK50 알고리즘 순위).

**추가 실험**
- [ ] 가정 민감도: batch, oven 선택 규칙, OIDT 정의
- [ ] 평가 횟수에 따른 HV 수렴, 알고리즘별 계산 시간
- [ ] BK20 적용. 추가 열(`Fixed_position`, `machines_ employees2_ME`, `extended_time`, `Employee_required`)에 맞는 전처리와 제약 확장이 필요하다.

**5. 결과 분석·보고서**
- [ ] 결과 분석, 시각화, 보고서 작성
