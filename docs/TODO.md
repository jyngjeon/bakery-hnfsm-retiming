# TODO (2026-11-24 기준)

## (A) 팀 결정 필요

이 항목들은 임의로 정하지 않는다. 결정이 나면 `PROGRESS.md` "모델링 가정"에 반영한다.

- [ ] **A1. OIDT 정의**
  - 선택지: (a) 구획별 점유구간 합집합(현재 코드), (b) 논문 M2 그대로(end−start−ΣPT, 동시 베이킹 PT 이중 차감)
  - 근거: random search만으로도 M2 값이 논문 PF* 최소 OIDT보다 낮아진다(BK15 19 < 72, BK50 1054 < 1243). 합집합은 논문 값보다 높게 머문다.
  - 권장: (a)를 주 목적함수로 쓰고 (b)를 민감도 지표로 함께 보고한다.
- [ ] **A2. infeasible 순서 처리**
  - 현재: `(1e9, 1e9)`. BK15 random 순서의 3.4%가 해당된다.
  - 선택지: (a) 현행 유지, (b) 근무시간 초과량에 비례하는 penalty, (c) repair(배치 실패 그룹을 앞으로 당겨 재시도 등), (d) constrained-dominance
  - 권장: (b) 또는 (d). 상수 penalty는 탐색 정보가 없다.
- [ ] **A3. 자원 tie-break 규칙**, 특히 오븐
  - 선택지: (a) first-fit 최저 인덱스(현재), (b) 이미 사용 중인 구획 우선(OIDT 감소), (c) 가장 일찍 비는 자원 / 최소 부하
  - 권장: 재현에는 (a)를 유지하고 문서화한다. (b)는 민감도 실험으로 돌린다. Retiming 비교와 섞이지 않게 B0·P1은 같은 규칙을 쓴다.
- [ ] **A4. 같은 그룹 co-baking 규칙**
  - 선택지: (a) 같은 그룹이면 어떤 겹침도 허용(현재), (b) 같은 구획에서는 ST·CT가 같을 때만 허용(Fig. 3 형태)
  - 권장: (a) 유지. 논문 본문(p.4, p.6)에 동시 시작 조건이 없다.
- [ ] **A5. batch 전개와 Group 18**
  - 선택지: (a) batch를 독립 그룹으로 전개(현재), (b) 전개하지 않음
  - Group 18 Dough C: (i) 2회 전개(현재), (ii) 1회만
  - 권장: (a)와 (i). BK15 CP-SAT 471이 논문 E1(≈471)과 일치한다. 다만 전개하지 않은 경우와 비교 실행은 아직 하지 않았다(확인 필요).
- [ ] **A6. "iteration"의 의미와 HV reference point**
  - 논문은 iteration 50/100/200/300의 정의를 밝히지 않는다. 선택지: (a) 세대 수(×population 50 = 최대 15,000 평가), (b) 평가 횟수
  - 권장: (a). 제안서의 "같은 평가 횟수 15,000회"와도 맞는다.
  - HV reference point는 논문에 값이 없다. 권장: B0·P1의 해를 합쳐 정규화한 뒤 (1.1, 1.1)을 쓴다(확인 필요).

## (B) Stage 2 전 필수 수정

- [x] **B1.** decoder와 CP-SAT의 UNLIMITED 기계 처리를 고친다. (2026-11-24 리팩토링 때 수정, `tests/test_decoder.py`)
- [ ] **B2.** BK50 Group 31의 2회차 Boxing 자원 공백을 처리한다(Manual로 보정할지 팀 확인).
- [ ] **B3.** 알고리즘 설정을 Table 5에 맞추고 (데모 스크립트는 seed 2001 고정만 반영)(population 50, SBX rate 1, polynomial mutation 1/NG, binary tournament) seed를 고정한다. 실행 설정을 기록한다.
- [x] **B4.** 원본 노트북 cell 14의 "논문 BK15 PF* 최소 makespan 약 471분" 표현. 노트북을 삭제해 해소. 보고서에는 출처를 CP-SAT 결과와 Fig. 7a 판독으로 적는다.
- [ ] **B5.** 모델링 가정(PROGRESS.md 5절)을 보고서용 문서로 확정한다. 대상은 OIDT 정의, batch, tie-break, co-baking, infeasible 처리다.

## (C) 남은 작업 (제안서 기준)

**Stage 1 마무리**
- [x] 논문 Table 1 손계산 예제를 대조한다. makespan 244, oven idle 53 (`tests/data/paper-table1-example.json`, `tests/test_decoder.py`)
- [ ] Gantt chart를 시각화하고 oven idle 구간과 OIDT 값을 대조한다.
- [ ] makespan 하한과 baseline을 점검한다. random search보다 좋은지 확인한다.

**Stage 2: 알고리즘 연결**
- [ ] NSGA-II를 Table 5 설정으로 정식 연결한다.
- [ ] SPEA2를 연결한다.
- [ ] OMOPSO를 연결한다(uniform + non-uniform mutation, Table 5 계수).
- [ ] GDE3를 연결한다(CR=1, F=0.4).
- [ ] SMPSO를 연결한다(Table 5 계수).

**Stage 3: 재현 실험 A**
- [ ] R0: random search와 원래 순서를 비교한다.
- [ ] R1: BK15·BK50 × 5종 × iteration 4종, 각 1 run
- [ ] R2: BK15·BK50 × 5종 × seed 10개, 300 iteration까지 실행하고 50·100·200·300 시점 결과를 저장
- [ ] 지표: PDS, MSF, DPF, HV/RHA, PCA + GMM cluster
- [ ] 통계 검정: Kruskal–Wallis, Wilcoxon, Holm
- [ ] 논문 PF*와 경향을 비교한다(E1≠E2, front 모양, BK50 알고리즘 순위).

**Stage 4: Retiming**
- [x] 명세(`proposal/proposal-idea-01-event-point-retiming.md`)대로 한 그룹 Event-Point Retiming을 구현한다. (2026-11-28: BK15·BK50 공통 최종 모듈, 성능 최적화·API 보완 완료)
- [x] 부분문제 검증: 소형 예제를 전수탐색해 비교한다. (266개 전체·두 정책, 17,712개 부분문제, 불일치 0건; pytest 68개 통과)
- [x] 제안서의 BK15 예비 검증(66개 중 54개 개선) 코드와 자료 위치를 확인한다. (원본 ZIP 확보·체크섬 고정·66개 재현; 별도 공유 경로는 `retiming.md`, `repro/retiming-evidence.json`)

**Stage 5: 개선안 비교**
- [ ] NSGA-II와 최종 Retiming API를 통합하고 수정된 실제 스케줄·목적값을 함께 보존한다.
- [ ] B0 vs P1: 같은 평가 횟수(15,000)와 같은 실행 시간 두 기준, seed 10개, Wilcoxon
- [ ] 통합 후 B0·P1의 통계적 성능을 검증한다. Retiming 자체의 시간 감소를 Pareto front·HV 향상으로 해석하지 않는다.
- [ ] Ablation(BK15): 자원 순서 변경 허용/고정, 경계 그룹만/전체 그룹

**추가 실험**
- [ ] 가정 민감도: batch, oven 선택 규칙, OIDT 정의
- [ ] 평가 횟수에 따른 HV 수렴, 알고리즘별 계산 시간
- [ ] BK20 적용. 추가 열(`Fixed_position`, `machines_ employees2_ME`, `extended_time`, `Employee_required`)에 맞는 전처리와 제약 확장이 필요하다.

**Stage 6**
- [ ] 결과 분석, 시각화, 보고서 작성
