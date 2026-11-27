# Retiming 사용 및 검증 재현

현재 `src/bakery/retiming.py`는 독립 구현·정확성 검증·성능 최적화를 마친 최종 Retiming 모듈이다. NSGA-II 통합과 B0·P1 최적화 성능 비교는 아직 수행하지 않았다. 이 문서는 로컬 기준 `4ac203adba09e3bf4d0c758f03f335be08e3dfd4` 위에서 검증한 코드와 보존된 결과를 설명한다. 이후 정상적인 commit에서도 아래 명령을 사용할 수 있으며, 과거 HEAD와 현재 HEAD가 같을 필요는 없다.

## 1. 알고리즘과 정확성 범위

한 번의 후처리에서 전개된 그룹 `g`의 모든 공정을 같은 정수 Δ만큼 이동한다. 나머지 그룹의 ST·CT와 전체 기계·오븐·직원 배정은 고정한다. WT와 no-wait를 유지하면서 자원 충돌, 직원 근무시간, 기존 makespan 상한으로 실행가능 정수 시작시각 구간을 계산한다. 각 구간의 양 끝점과 관련 OIDT 꺾임점을 평가하고, 전체 후보에서 최선의 그룹 이동 한 번만 적용한다.

기본 정책은 오븐의 최초 시작 또는 최종 종료를 결정하는 경계 그룹 선별, 자원 처리순서 변경 허용이다. 수락 조건은 makespan·OIDT 모두 비악화이고 하나 이상 엄격히 개선되는 것이다. 동률은 `(OIDT, makespan, g, T_g)` 순서로 결정한다. 개선이 없으면 원본과 내용이 같은 별도 DataFrame을 반환한다.

OIDT는 구획별 점유구간 합집합 기준이며, 같은 그룹의 공동 베이킹과 UNLIMITED 용량 해석은 현재 팀 코드를 따른다. 이는 원저자 코드와 동일하다고 입증된 해석이 아니다. 모델 근거는 원논문 PDF p.5 M1–M2, p.6 M6·M8–M9·M12–M13·M17–M18이며, 기존 쟁점은 [paper-conformance.md](paper-conformance.md)와 [TODO.md](TODO.md)에 남긴다.

정확성 보장은 **자원 배정과 다른 그룹 시각을 고정한 한 그룹 이동 부분문제**에 한정된다. 경계 그룹 선별은 최소 OIDT를 위한 것으로, 전체 그룹의 Makespan-only 개선이나 OIDT 동률에서 같은 makespan까지 보장하지 않는다. 전체 스케줄의 전역최적성, NSGA-II Pareto front·HV 향상을 주장하지 않는다.

## 2. 팀원용 최소 API 예제

아래 코드는 clone한 프로젝트 루트에서 실행하는 Python 예제다. 재사용 함수는 `src/bakery/`, 실험 실행은 `experiments/`에 둔다.

```python
from bakery.decoder import INFEASIBLE, hnfsm_decode
from bakery.paths import processed_json
from bakery.retiming import PreparedRetimingInstance, schedule_for_export

json_path = processed_json("BK15")
prepared = PreparedRetimingInstance(json_path)
instance = prepared.instance
order = instance["group_ids"]

ms, oidt, base_schedule = hnfsm_decode(instance, order, return_schedule=True)
if ms >= INFEASIBLE or base_schedule is None:
    # 호출자의 기존 infeasible penalty를 그대로 유지한다.
    objectives = (INFEASIBLE, INFEASIBLE)
    schedule = None
else:
    result = prepared.retime(base_schedule)
    makespan, oidt = result.makespan, result.oidt
    schedule = result.schedule
    objectives = (makespan, oidt)
    assert result.checker["is_valid"]
    assert result.invariants["is_valid"]
    export_schedule = schedule_for_export(schedule)
    print(objectives, result.moved_group, result.delta)
```

한 인스턴스당 `prepared`와 decoder용 `instance`를 한 번 생성하고, 새 상세 스케줄마다 `prepared.retime()`을 호출한다. `prepared.instance`는 독립 복사본이므로 평가마다 다시 요청할 필요가 없다. 입력 DataFrame은 수정하지 않는다. `result`는 실제 스케줄, 목적값, 이동 여부·그룹·전후 `T_g`·Δ, Checker·불변조건 보고서, 후보 수와 실행시간을 제공한다.

- `prepared.retime(schedule_df)`의 기본값은 `boundary_only=True, preserve_order=False`다.
- `boundary_only=False`는 전체 그룹 탐색, `preserve_order=True`는 기존 자원 처리순서 고정 ablation이다.
- `retime_schedule(instance, schedule_df, json_path, ...)`도 유지한다. instance와 JSON이 다르면 거부한다.
- JSON 내용 SHA-256이 바뀌면 준비 객체·decoder instance를 다시 생성한다. 파일 크기·수정시각이 같은 변경도 감지한다.
- 반환 DataFrame은 입력 행 순서·index·열 순서를 유지한다. CSV 저장·간트 차트 생성 직전에만 `schedule_for_export()`로 `(ST,g,p,s)` 정렬한다.
- 수정된 `result.schedule`과 목적값을 함께 보존한다. 그룹 순서로 HNFSM을 다시 실행하면 Retiming 이동 효과가 사라진다.
- 기존 Checker 함수는 모든 규칙을 계속 검사한다. 내부 adapter는 현재 Checker가 `.columns`와 `.iterrows()`의 mapping 행을 사용한다는 규약에 의존한다. Checker가 다른 DataFrame 기능을 사용하도록 바뀌면 adapter 호환성을 다시 검증한다.

기본 순서의 예상 목적값은 BK15 `(519,273) → (519,272)`, BK50 `(1202,2409) → (1202,2357)`이다. 새 해를 보고할 때는 Checker 위반 0건을 확인한다.

## 3. 환경과 저장소만으로 가능한 검증

Python 3.12와 uv를 사용한다. 의존성을 추가하거나 lock을 재작성할 필요는 없다.

```text
uv sync --locked
uv run --locked pytest
uv run --locked pytest tests/test_retiming.py
uv run --locked python experiments/stage4-retiming-validation.py --scope current
```

`--scope current`가 기본값이다. 현재 정제 JSON으로 인스턴스별 100개의 실행가능 스케줄을 생성한다. 각 인스턴스는 원래 순서 1개와 고정 seed의 random 순서를 사용한다. BK15 seed는 20261126, BK50은 20261127이다. Decoder 실패와 실제 검증 개수는 분리해 기록한다. 대표 표본은 인스턴스별 원래 순서와 첫 두 실행가능 random 순서이며, 독립 전수탐색은 자원 순서 변경 허용·고정 양쪽에 적용한다.

출력은 새로운 `results/stage4-retiming-validation-<UTC timestamp>/`다. `summary.json`에 요청 scope와 완료 여부를 기록하고, 66개 회귀 검증을 요청하지 않았다는 사실을 명시한다. 이 명령의 성공은 저장소 기반 신규 200개 범위의 성공이다. 과거 66개를 검증했다는 뜻은 아니다.

## 4. 외부 파일럿 자료와 66개 회귀 검증

외부 자료의 체크섬·필수 파일 목록은 [repro/retiming-evidence.json](../repro/retiming-evidence.json)에 고정했다. 원본 ZIP과 추출 파일은 별도 팀 공유 대상으로 두며 GitHub commit에는 포함하지 않는다.

| 원본 파일 | 크기(bytes) | SHA-256 | 역할 |
|---|---:|---|---|
| `BK15_NSGAII_pilot_verified(2).zip` | 2,221,187 | `0c6107182f4d742dc5c7a50b9b2aaa975a849958b65d401bda57db78a761028a` | 저장된 66개 스케줄, parsed metadata, raw-XLSX Checker·frozen HNFSM |
| `EventPoint_Retiming_최종검토_검증자료.zip` | 26,078 | `ac44ff8e84f002c1fa95723e16c8a70341792ce3a1d1397cc48fdb4a57175ea4` | 과거 Retiming 코드와 기준 결과 |

ZIP을 `external/retiming-archives/`에 받은 뒤 원본 파일명을 유지하고 다음과 같이 해제한다. `external/`는 Git 공유 대상에서 제외한다.

```text
uv run --locked python -m zipfile -e "external/retiming-archives/BK15_NSGAII_pilot_verified(2).zip" external/retiming-source/pilot
uv run --locked python -m zipfile -e "external/retiming-archives/EventPoint_Retiming_최종검토_검증자료.zip" external/retiming-source/event-point
uv run --locked python experiments/stage4-retiming-validation.py --scope legacy
uv run --locked python experiments/stage4-retiming-validation.py --scope all
```

필수 경로는 `external/retiming-source/pilot/optimization_pilot/`와 `external/retiming-source/event-point/`다. `--legacy-source`로 추출 루트를 지정할 수도 있다. 실행 전 필수 추출 파일의 SHA-256을 검사한다. 누락·불일치는 오류로 중단하며, 전체 성공으로 처리하지 않는다.

`--scope legacy`는 66개를 현재 형식으로 매핑해 검사하고 기존 코드·기준 목적값과 대조한다. `--scope all`은 이 범위와 신규 200개를 모두 실행한다. 기존 스크립트는 새 scratch 복사본에서만 실행한다. `--skip-legacy-rerun`은 원본 스크립트 재실행만 명시적으로 제외하는 옵션이며, 해당 선택을 결과 config에 기록한다. 이 경우에도 66개 스케줄과 기준 결과 파일은 필요하다.

성능 비교의 66개 입력을 로드하는 데 필요한 최소 subset은 parsed JSON 1개와 `*_pareto_schedules.json.gz` 15개, 총 **246,500bytes**다. 전체 원본 코드 재실행에는 위 ZIP 두 개의 추가 파일이 필요하다. 중복되는 평가 로그·그림·과거 온라인 최적화 결과 전체를 Git에 넣을 필요는 없다.

두 ZIP에서 별도 LICENSE/COPYING/NOTICE 파일을 발견하지 못했다. README에 명시된 원본 베이커리 데이터의 CC BY 4.0이 파일럿 코드·생성 스케줄의 라이선스까지 확정해 주지는 않는다. 공개 재배포 권한은 자료 제공자와 확인하고, 그 전에는 ZIP을 팀 내 별도 전달한다. 이 문서는 새 라이선스를 부여하지 않는다.

## 5. 최적화 전 기준과 성능·전수탐색 재현

최적화 전 코드와 당시 테스트는 `repro/retiming-baseline/`에 보존했다. 생산 패키지에 설치되지 않으며 `importlib`로 비교 실험에서만 읽는다.

| 기준 파일 | 크기(bytes) | SHA-256 |
|---|---:|---|
| `src/bakery/retiming.py` | 16,462 | `55ca38f40e93f710a4a977b8e34631bcac83dab9ba9bf200e210f0662a01a9d3` |
| `tests/test_retiming.py` | 12,482 | `596bfa6b4e398009259b57af852edaa91ec099baa3a0e0bb0f2d717d13791796` |

`manifest.json`에는 원본 리뷰 ZIP 해시와 당시 revision도 기록한다. 실행 시 기준 파일 해시를 검사한다. 현재 HEAD·브랜치가 당시와 같아야 한다는 조건은 없고, 각 실행의 코드·데이터 해시와 실제 revision을 새로 기록한다. 실행 중 코드·데이터 또는 config가 바뀌면 같은 출력 디렉터리를 재사용하지 못한다. Git metadata가 없는 source archive에서는 revision을 없는 것으로 기록하고 파일 해시를 사용한다.

`.gitattributes`는 새 Retiming 소스·기준 사본·최종 결과의 checkout 줄바꿈 변환을 제한한다. SHA-256으로 보존한 파일이 Windows/Linux의 Git 설정 때문에 다른 바이트로 바뀌는 것을 방지하며, 기존 팀원 소스·데이터에는 적용하지 않는다.

먼저 입력·기준 파일만 확인할 수 있다. 이 명령은 알고리즘 검증 완료를 의미하지 않는다.

```text
uv run --locked python experiments/stage4-retiming-performance.py --phase inputs --corpus current
uv run --locked python experiments/stage4-retiming-performance.py --phase inputs --corpus all
```

독립 전수탐색과 성능 비교는 다음과 같다.

```text
uv run --locked python experiments/stage4-retiming-performance.py --phase exhaustive --corpus current
uv run --locked python experiments/stage4-retiming-performance.py --phase equivalence --corpus all
uv run --locked python experiments/stage4-retiming-performance.py --phase exhaustive --corpus all
uv run --locked python experiments/stage4-retiming-performance.py --phase benchmark --corpus all
uv run --locked python experiments/stage4-retiming-performance.py --phase all --corpus all
```

`current`는 저장소의 `bk15-details.json`·`bk50-details.json`에 보존된 순서로 신규 200개를 재생성한다. 외부 66개를 포함하지 않는 별도 범위이며 config·표본 수에 명시한다. `all`은 외부 자료까지 포함한 266개다. `--legacy-pilot`로 `optimization_pilot` 경로를 지정할 수 있다. 외부 자료가 없는데 `all`을 요청하면 중단한다.

각 명령은 새로운 `results/stage4-retiming-performance-<UTC timestamp>/`에 저장한다. 여러 phase를 한 실행으로 묶으려면 같은 `--output results/<새-실험명>`과 같은 config를 사용한다. 이미 존재하는 phase 결과는 덮어쓰지 않는다. `--phase finalize`는 해당 실행의 equivalence·exhaustive·benchmark 결과와 pytest를 확인해 요약한다. `--phase all`은 필요한 phase와 finalize를 순서대로 수행한다. 리뷰 ZIP은 기본 생성하지 않으며, 처음 실행부터 `--archive <새-ZIP-경로>`를 지정하면 마지막에 생성한다. 기존 리뷰 ZIP은 덮어쓰지 않는다.

성능 비교는 warm-up 1회 후 5회 반복하고 평균·중앙값·P95를 기록한다. 기준·기존 호출·준비 객체 재사용 방식을 같은 스케줄과 Checker 범위로 비교한다. HNFSM `return_schedule=False/True`와 실제 HNFSM→Retiming 전체 wall time을 별도로 기록한다. 계측용 단계 시간과 비계측 반복 성능을 구분하며, nested 시간을 중복 합산하지 않는다.

## 6. 보존된 최종 결과

정확성 자료는 [최종 validation 폴더](../results/stage4-retiming-validation-20261126T105021665036Z/), 성능 자료는 [최종 performance 폴더](../results/stage4-retiming-performance-20261127T153937355670Z/)를 읽는다. 과거 JSON·CSV는 현재 코드 해시로 재작성하지 않는다. 첫 검증 결과는 최적화 전 소스 해시, 성능 결과는 이후 최적화 소스 해시를 기록하고 있다.

| 항목 | 확인된 결과 |
|---|---|
| pytest | 기존 48개 유지 + 회귀 20개 = 68개 통과 |
| 기존 BK15 | 66개, 순서 변경 허용 54개 개선 / 고정 48개 개선 |
| 신규 스케줄 | BK15·BK50 각 100개, 각 96개 OIDT 개선 |
| 평균 OIDT 감소 | BK15 58.69분 / BK50 61.06분; 개선 없는 표본 포함 |
| 생성 실패 | BK15 102회 시도 중 2개 실패, BK50 100회 중 0개 |
| 전후 결과 비교 | 266개 × 두 순서 정책 × 경계/전체 = 1,064개 모두 일치 |
| 그룹·정책 비교 | 17,712개, 실행가능 시각 집합·후보·선택 이동 일치 |
| 독립 전수탐색 | 266개 전체, 18,606,440개 정수 시각 검사, 불일치 0건 |
| Checker·불변조건·Pareto 비악화 | 위반 0건 |

성능 반복 측정의 BK15 입력은 기존 66개와 신규 100개를 합친 166개(방법별 830회), BK50은 신규 100개(방법별 500회)다. 같은 입력끼리 비교한 평균은 다음과 같다.

| 경로 | BK15(ms) | BK50(ms) |
|---|---:|---:|
| 기준 Retiming | 21.92 | 72.26 |
| 최적화 후 기존 호출 | 12.09 | 29.55 |
| 최적화 후 준비 객체 재사용 | 9.97 | 24.63 |
| 준비 객체 재사용의 시간 감소율 | 54.53% | 65.91% |
| HNFSM 단독, 상세 스케줄 없음 | 2.22 | 30.46 |
| HNFSM 단독, 상세 스케줄 있음 | 3.79 | 33.86 |
| 실제 HNFSM→기준 Retiming | 24.81 | 102.59 |
| 실제 HNFSM→최적화 Retiming | 13.53 | 57.72 |

이는 **Retiming의 구현 비용 감소**다. HNFSM 단독 평가보다 후처리·검증의 추가 비용은 남는다. NSGA-II에 통합한 후의 Pareto front·HV 성능이나 통계적 우위는 검증하지 않았다. 시간은 하드웨어·부하에 의존하므로 다른 장비에서 절대값 일치를 요구하지 않는다.

## 7. GitHub 공유 범위와 후속 작업

권장 commit 파일별 크기·해시·포함 이유는 [retiming-sharing-files.tsv](retiming-sharing-files.tsv)에 정리한다. 최종 소스 5개, 이 문서와 진행 문서, 선택한 JSON·CSV·pytest 기록, 기준 소스와 자료 manifest를 공유한다. `.venv`, scratch, external ZIP, 리뷰 ZIP, `.prof`, 중간 검증 결과는 제외하되 로컬에서는 보존한다.

알려진 제외 파일의 크기·이유는 [retiming-sharing-exclusions.tsv](retiming-sharing-exclusions.tsv)에 기록했다. 환경·캐시 폴더는 전체 순회하지 않았으므로 크기를 측정했다고 보고하지 않는다.

이 분기의 로컬 기준은 오래된 `4ac203ad…`다. 2026-11-28 읽기 전용 확인 당시 원격 main은 `1ec9e4524d0139881b398b5b6aee7a80802acba6`였다. 원격 후속 기록은 가져오거나 덮어쓰지 않았다. 이후 사용자가 최신 main과 문서 충돌을 검토하고, 팀원 코드와 합친 환경에서 다시 회귀 검증해야 한다. 이 문서가 팀원의 NSGA-II 진행 상태를 대신 판정하지 않는다.

남은 작업은 NSGA-II 평가기 통합, 동일 평가 횟수·동일 실행시간 B0/P1 비교, 통계 검증, 나머지 알고리즘 연결, 본 실험과 최종 보고서다. BK50 Boxing·OIDT 해석·예산 등 팀 결정 사항은 이 작업에서 바꾸지 않았다.

## 8. 이번 공유 준비에서 실제 확인한 범위

2026-11-28 공유 준비 검증은 [repro/retiming-sharing-checks.json](../repro/retiming-sharing-checks.json)에 기록했다. 원래 환경과 별도 clean 복사본 모두 pytest 68개와 위 API 예제를 통과했다. clean 복사본에는 scratch·external·기존 `.venv`를 복사하지 않았고, 공유 파일과 기존 추적 파일만 넣은 뒤 `uv sync --locked --offline`으로 별도 환경을 설치했다. uv 패키지 캐시는 같은 컴퓨터의 기존 캐시를 재사용했으므로 새 OS에서의 설치 검증으로 해석하지 않는다.

저장소 전용 신규 200개 검증은 원래 환경과 clean 환경 모두 재현됐다. 별도 외부 자료를 제공한 환경에서는 66개 회귀 검증도 통과했다. 성능 입력 preflight는 저장소 전용 200개와 외부 자료 포함 266개를 각각 확인했다. 자료 누락, 기준 해시 불일치, 과거 결과 폴더 재사용은 의도적으로 검사해 오류로 거부되는 것을 확인했다. finalize의 Git metadata 없음·다른 revision 허용은 과거 보고서의 바이트를 바꾸지 않은 별도 fixture 복사본에서 I/O 동작만 시험했다.

이번 정리에서 전체 성능 benchmark와 18,606,440회 전수탐색을 다시 실행하지는 않았다. 해당 전체 수치는 보존된 최종 결과에 근거한다. 재현 스크립트의 변경은 scope·경로·입력 해시·Git provenance·출력 보호·UTF-8 처리에 한정되며, 생산 모듈·독립 검증기·테스트와 계산 조건을 보존했다.
