"""Build status/index.html: a one-page project status board for the team (Korean).

Sources (read only):
- docs/TODO.md                       checklists (B) and (C), parsed from "- [x]" / "- [ ]" lines
- results/stage2-nsga2/summary.json  NSGA-II fronts and indicators
- bakery.paper_ref                   paper reference values
Curated text (next actions, open questions) lives in NEXT_ACTIONS / OPEN_QUESTIONS below;
edit them together with docs/TODO.md.

Usage: uv run python status/build-status.py
Output: status/index.html (self-contained, no external assets)
"""

from __future__ import annotations

import html
import re
from datetime import date

from bakery.io import _git_rev, load_json
from bakery.paper_ref import PAPER
from bakery.paths import REPO_ROOT, RESULTS

TODAY = date(2026, 11, 27)
OUT = REPO_ROOT / "status" / "index.html"

# Work order changed on 2026-11-27 (docs/PROJECT.md section 7, docs/TODO.md (C)).
# "section" = the bold heading in docs/TODO.md (C); progress and status are computed from its checkboxes.
STAGES = [
    {"no": 1, "name": "NSGA-II 구현·검증 마무리", "section": "1. NSGA-II 구현·검증 마무리",
     "note": "NSGA-II Table 5 연결·R1/R2·논문 대조 완료. Gantt, makespan 하한, R0, BK50 OIDT 원인 확인 남음"},
    {"no": 2, "name": "Retiming 구현·검증", "section": "2. Retiming",
     "note": "명세만 있음. 전수탐색 부분문제 검증, 예비 검증 코드 위치 확인"},
    {"no": 3, "name": "B0 vs P1·Ablation", "section": "3. 개선안 비교 (B0 vs P1)",
     "note": "Retiming 구현 후 착수. NSGA-II만 사용"},
    {"no": 4, "name": "나머지 알고리즘·재현 실험 A 완성", "section": "4. 나머지 알고리즘과 재현 실험 A 완성",
     "note": "SPEA2 → OMOPSO → GDE3 → SMPSO 연결, 5종 PF*·GMM·통계 검정"},
    {"no": 5, "name": "결과 분석·보고서", "section": "5. 결과 분석·보고서",
     "note": "제안서 일정 12/1–12/7. 모델링 가정(B5) 문안은 먼저 써도 됨"},
]
STATUS_LABEL = {"done": "완료", "mostly": "대부분 완료", "partial": "진행 중", "todo": "미착수"}

NEXT_ACTIONS = [
    ("1단계", "Gantt chart로 oven idle·OIDT 대조",
     "oven idle 구간을 그림으로 보고 OIDT 값과 대조. BK50 최소 OIDT 1208(논문 E2 1243보다 낮음)의 원인도 함께 확인."),
    ("1단계", "makespan 하한, R0(random search·원래 순서) 점검",
     "NSGA-II 결과가 random search보다 좋은지 확인. BK15 CP-SAT 471, BK50 CP-SAT 931과 비교."),
    ("2단계", "Event-Point Retiming 구현",
     "명세: <code>docs/proposal/proposal-idea-01-event-point-retiming.md</code>. 제안서 BK15 예비 검증(66개 중 54개 개선) 코드 위치 확인."),
    ("2단계", "Retiming 부분문제 검증",
     "소형 예제에서 전수탐색 결과와 비교. 결과 스케줄은 checker 위반 0건 확인."),
    ("3단계", "B0 vs P1, Ablation",
     "같은 평가 횟수(15,000)와 같은 실행 시간 두 기준, seed 10개, Wilcoxon. B0 = <code>experiments/stage2-nsga2.py</code> 설정."),
    ("4단계", "SPEA2 → OMOPSO → GDE3 → SMPSO 연결",
     "<code>experiments/stage2-nsga2.py</code>와 같은 seed·snapshot·출력 형식. 5종 합집합으로 PF*와 지표 재계산."),
]

OPEN_QUESTIONS = [
    ("B2", "BK50 Group 31 2회차 Boxing 자원 공백",
     "원본 칸이 비어 NONE으로 처리 중. 1회차처럼 Manual로 보정할지 결정 필요. 바꾸면 BK50 결과 재실행."),
    ("NSGA-II", "BK50 최소 OIDT 1208이 논문 E2 1243보다 낮음",
     "오븐 구획 수(9 vs 10)나 OIDT 정의(합집합 vs M2) 차이가 원인일 수 있음. 해당 스케줄 Gantt로 확인 필요."),
    ("NSGA-II", "iteration 경계: 초기 population = 1세대",
     "g세대 = 50·g회 평가(300세대 = 15,000회)로 정함. 1세대 차이라 영향은 작지만 팀 동의 필요."),
    ("2단계", "Retiming 예비 검증 코드·자료 위치",
     "제안서의 BK15 66개 중 54개 개선, HV +2.08% 결과의 출처가 저장소에 없음."),
]

DECISIONS = [
    ("A1", "OIDT 정의", "구획별 점유구간 합집합(주) + 논문 M2 병기"),
    ("A2", "infeasible 처리", "(1e9, 1e9) 유지 + 발생률 보고 (NSGA-II: BK15 0.022%, BK50 0%)"),
    ("A3", "자원 tie-break", "first-fit. used_first·min_idle은 민감도 실험"),
    ("A4", "같은 그룹 co-baking", "겹침 형태 제한 없음"),
    ("A5", "batch 전개", "독립 그룹으로 전개, Group 18 Dough C 2회"),
    ("A6", "iteration·HV", "iteration = 세대(50×300 = 15,000회), 주 지표 RHA, RV (1.1, 1.1)"),
]

def inline_md(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)
    return t


def parse_todo() -> list[dict]:
    """Sections (B) and (C) of docs/TODO.md as [{section, items: [{done, text, notes}]}]."""
    lines = (REPO_ROOT / "docs" / "TODO.md").read_text(encoding="utf-8").splitlines()
    sections, cur, in_scope = [], None, False
    for line in lines:
        if line.startswith("## "):
            in_scope = line.startswith("## (B)") or line.startswith("## (C)")
            if line.startswith("## (B)"):
                cur = {"section": "(B) Stage 2 전 필수 수정", "items": []}
                sections.append(cur)
            continue
        if not in_scope:
            continue
        m = re.match(r"^\*\*(.+)\*\*\s*$", line)
        if m:
            cur = {"section": m.group(1), "items": []}
            sections.append(cur)
            continue
        m = re.match(r"^- \[( |x)\] (.+)$", line)
        if m and cur is not None:
            cur["items"].append({"done": m.group(1) == "x", "text": m.group(2), "notes": []})
            continue
        m = re.match(r"^\s+- (.+)$", line)
        if m and cur is not None and cur["items"]:
            cur["items"][-1]["notes"].append(m.group(1))
    return [s for s in sections if s["items"]]


# ---------- SVG helpers ----------

def scatter_svg(inst: str, ours: list, paper: list, w=520, h=320) -> str:
    pad_l, pad_r, pad_t, pad_b = 56, 16, 16, 44
    pts = ours + paper
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    dx, dy = (x1 - x0) * 0.08 or 1, (y1 - y0) * 0.08 or 1
    x0, x1, y0, y1 = x0 - dx, x1 + dx, y0 - dy, y1 + dy
    sx = lambda x: pad_l + (x - x0) / (x1 - x0) * (w - pad_l - pad_r)
    sy = lambda y: h - pad_b - (y - y0) / (y1 - y0) * (h - pad_t - pad_b)

    def ticks(a, b, n=5):
        step = (b - a) / n
        mag = 10 ** len(str(int(step))) / 10
        step = max(1, round(step / mag) * mag)
        t = (int(a // step) + 1) * step
        out = []
        while t < b:
            out.append(t)
            t += step
        return out

    g = []
    for t in ticks(y0, y1):
        g.append(f'<line class="grid" x1="{pad_l}" x2="{w - pad_r}" y1="{sy(t):.1f}" y2="{sy(t):.1f}"/>'
                 f'<text class="tick" x="{pad_l - 6}" y="{sy(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    for t in ticks(x0, x1):
        g.append(f'<text class="tick" x="{sx(t):.1f}" y="{h - pad_b + 16}" text-anchor="middle">{t:g}</text>')
    g.append(f'<line class="axis" x1="{pad_l}" x2="{w - pad_r}" y1="{h - pad_b}" y2="{h - pad_b}"/>')
    g.append(f'<text class="axlabel" x="{(pad_l + w - pad_r) / 2}" y="{h - 6}" text-anchor="middle">Makespan [min]</text>')
    g.append(f'<text class="axlabel" transform="translate(14,{(pad_t + h - pad_b) / 2}) rotate(-90)" '
             f'text-anchor="middle">OIDT [min]</text>')

    def series(points, cls, marker):
        pts = sorted(points)
        path = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(pts))
        out = [f'<path class="line {cls}" d="{path}"/>']
        for x, y in pts:
            label = f"{'재현' if cls == 'ours' else '논문'} ({x:g}, {y:g})"
            if marker == "circle":
                out.append(f'<circle class="pt {cls}" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5"><title>{label}</title></circle>')
            else:
                out.append(f'<rect class="pt {cls}" x="{sx(x) - 4.5:.1f}" y="{sy(y) - 4.5:.1f}" width="9" height="9">'
                           f'<title>{label}</title></rect>')
        return "".join(out)

    g.append(series(paper, "paper", "square"))
    g.append(series(ours, "ours", "circle"))
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{inst} PF* 비교">{"".join(g)}</svg>')


def trend_svg(inst: str, metric: str, ours_med: dict, ours_s1: dict, paper: dict, w=250, h=170) -> str:
    its = [50, 100, 200, 300]
    vals = list(ours_med.values()) + list(paper.values()) + list(ours_s1.values())
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    pl, pr, pt, pb = 40, 10, 22, 28
    sx = lambda i: pl + (i - 50) / 250 * (w - pl - pr)
    sy = lambda v: h - pb - (v - lo) / (hi - lo) * (h - pt - pb)
    g = [f'<text class="charttitle" x="{pl}" y="14">{inst} · {metric}</text>']
    for v in (lo + (hi - lo) * k / 3 for k in range(1, 3)):
        g.append(f'<line class="grid" x1="{pl}" x2="{w - pr}" y1="{sy(v):.1f}" y2="{sy(v):.1f}"/>'
                 f'<text class="tick" x="{pl - 4}" y="{sy(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
    for i in its:
        g.append(f'<text class="tick" x="{sx(i):.1f}" y="{h - pb + 14}" text-anchor="middle">{i}</text>')
    g.append(f'<line class="axis" x1="{pl}" x2="{w - pr}" y1="{h - pb}" y2="{h - pb}"/>')
    for d, cls, mk in ((paper, "paper", "rect"), (ours_med, "ours", "circle")):
        path = " ".join(f"{'M' if k == 0 else 'L'}{sx(i):.1f},{sy(d[i]):.1f}" for k, i in enumerate(its))
        g.append(f'<path class="line {cls}" d="{path}"/>')
        for i in its:
            lab = f"{'논문' if cls == 'paper' else '재현 중앙값'} {i}세대: {d[i]:.1f}"
            if mk == "circle":
                g.append(f'<circle class="pt {cls}" cx="{sx(i):.1f}" cy="{sy(d[i]):.1f}" r="4"><title>{lab}</title></circle>')
            else:
                g.append(f'<rect class="pt {cls}" x="{sx(i) - 3.5:.1f}" y="{sy(d[i]) - 3.5:.1f}" width="7" height="7">'
                         f'<title>{lab}</title></rect>')
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{inst} {metric} 추이">{"".join(g)}</svg>'


# ---------- page ----------

def build() -> str:
    todo = parse_todo()
    n_all = sum(len(s["items"]) for s in todo)
    n_done = sum(i["done"] for s in todo for i in s["items"])
    summ = load_json(RESULTS / "stage2-nsga2" / "summary.json")
    insts = summ["instances"]

    by_section = {sec["section"]: sec["items"] for sec in todo}
    for st in STAGES:
        items = by_section[st["section"]]
        st["done"], st["total"] = sum(i["done"] for i in items), len(items)
        st["status"] = "done" if st["done"] == st["total"] else ("partial" if st["done"] else "todo")
    current = next(st for st in STAGES if st["status"] != "done")

    kpis = [
        (f"{n_done}/{n_all}", "TODO (B)(C) 완료 항목"),
        ("6/6", "(A) 팀 결정 완료"),
        (f"{current['no']}단계", f"현재: {current['name']}"),
        ("1/5", "알고리즘 연결 (NSGA-II, 나머지는 4단계)"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="kpi-v">{v}</div><div class="kpi-l">{l}</div></div>' for v, l in kpis)

    stage_cards = "".join(
        f'<div class="stage {st["status"]}{" current" if st is current else ""}"><div class="stage-h"><span class="badge {st["status"]}">'
        f'{STATUS_LABEL[st["status"]]}</span><span class="stage-no">{st["no"]}단계</span></div>'
        f'<div class="stage-name">{html.escape(st["name"])}</div>'
        f'<div class="prog"><span class="prog-bar"><span style="width:{100 * st["done"] / st["total"]:.0f}%"></span></span>'
        f'{st["done"]}/{st["total"]}</div>'
        f'<div class="stage-note">{html.escape(st["note"])}</div></div>' for st in STAGES)

    next_rows = "".join(
        f'<tr><td class="num">{k}</td><td class="nowrap">{st}</td>'
        f'<td><strong>{t}</strong><div class="sub">{d}</div></td></tr>'
        for k, (st, t, d) in enumerate(NEXT_ACTIONS, 1))

    q_rows = "".join(f'<li><span class="tag">{a}</span><strong>{t}</strong><div class="sub">{d}</div></li>'
                     for a, t, d in OPEN_QUESTIONS)

    todo_html = []
    for s in todo:
        done = sum(i["done"] for i in s["items"])
        pct = 100 * done / len(s["items"])
        items = "".join(
            f'<li class="{"done" if i["done"] else "open"}"><span class="box" aria-hidden="true">'
            f'{"✓" if i["done"] else ""}</span><div><span class="sr">{"완료" if i["done"] else "미완료"}: </span>'
            f'{inline_md(i["text"])}'
            + "".join(f'<div class="sub">{inline_md(n)}</div>' for n in i["notes"]) + "</div></li>"
            for i in s["items"])
        todo_html.append(
            f'<details class="todo" {"open" if done < len(s["items"]) else ""}><summary>'
            f'<span class="todo-title">{html.escape(s["section"])}</span>'
            f'<span class="prog"><span class="prog-bar"><span style="width:{pct:.0f}%"></span></span>'
            f'{done}/{len(s["items"])}</span></summary><ul>{items}</ul></details>')

    dec_rows = "".join(f"<tr><td class='num'>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in DECISIONS)

    # NSGA-II comparison
    charts, rows = [], []
    for inst in ("BK15", "BK50"):
        v = insts[inst]
        ours = [tuple(int(x) for x in p) for p in v["pf_star"]]
        pap = [tuple(p) for p in PAPER[inst]["pf_star"]]
        dom = sum(any(q[0] <= p[0] and q[1] <= p[1] and q != p for q in pap) for p in ours)
        charts.append(f'<figure><figcaption>{inst} PF*</figcaption>{scatter_svg(inst, ours, pap)}</figure>')
        mb = v["metrics_by_iteration"]
        rows.append(
            f"<tr><td>{inst}</td><td>{pap[0]} → {pap[-1]}</td><td>{ours[0]} → {ours[-1]}</td>"
            f"<td>{dom}/{len(ours)}</td>"
            f"<td>{PAPER[inst]['nsga2_rha'][50]:g} → {PAPER[inst]['nsga2_rha'][300]:g}</td>"
            f"<td>{mb['50']['RHA']['median']:.0f} → {mb['300']['RHA']['median']:.0f}</td>"
            f"<td>{v['infeasible_rate'] * 100:.3f}%</td><td>{'PASS' if v['all_fronts_checker_valid'] else 'FAIL'}</td></tr>")
    trends = []
    for inst in ("BK15", "BK50"):
        mb = insts[inst]["metrics_by_iteration"]
        for metric, pk in (("RHA", "nsga2_rha"), ("DPF_raw", "nsga2_dpf")):
            med = {int(k): mb[k][metric]["median"] for k in mb}
            s1 = {int(k): mb[k][metric]["seed1"] for k in mb}
            trends.append(trend_svg(inst, "RHA [%]" if metric == "RHA" else "DPF [min]", med, s1, PAPER[inst][pk]))

    rev = _git_rev()
    links = [
        ("docs/TODO.md", "할일 원본"), ("docs/PROGRESS.md", "진행 현황·모델링 가정"),
        ("docs/decisions-A.md", "(A) 결정 자료"), ("docs/paper-conformance.md", "원논문 적합성"),
        ("notebooks/stage2-nsga2.ipynb", "NSGA-II 논문 대조 노트북"), ("docs/PROJECT.md", "계획·수행 순서"),
    ]
    link_html = "".join(f'<a href="../{p}">{l}<span>{p}</span></a>' for p, l in links)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>팀13 HNFSM 재현·Retiming 현황판</title>
<style>{CSS}</style>
</head>
<body>
<div class="viz-root">
<header>
  <div class="eyebrow">IIE4124 팀13 · Babor et al. (2023) HNFSM 재현 + Event-Point Retiming</div>
  <h1>프로젝트 현황판</h1>
  <p class="lede">기준 {TODAY.isoformat()} · git <code>{rev}</code> · <code>uv run python status/build-status.py</code>로 다시 생성</p>
</header>

<section class="kpis">{kpi_html}</section>

<section>
  <h2>진행 순서 (2026-11-27 변경)</h2>
  <p class="desc">NSGA-II로 구현·검증 → Retiming → B0 vs P1을 먼저 끝내고, 나머지 알고리즘 4종은 그 뒤에 덧붙인다. 진행 막대는 <code>docs/TODO.md</code> (C)의 체크박스 수다.</p>
  <div class="stages">{stage_cards}</div>
</section>

<section class="two">
  <div>
    <h2>다음 할일 (우선순위 순)</h2>
    <div class="card"><table class="tbl"><thead><tr><th>#</th><th>단계</th><th>내용</th></tr></thead>
    <tbody>{next_rows}</tbody></table></div>
  </div>
  <div>
    <h2>팀 확인 필요</h2>
    <ul class="card qlist">{q_rows}</ul>
  </div>
</section>

<section>
  <h2>최근 결과: NSGA-II (Table 5) vs 논문</h2>
  <p class="desc">BK15·BK50, seed 10개 × 300세대. 재현 PF*는 NSGA-II 결과만 합친 잠정값이고, 논문 PF*는 5종 합집합(그림 판독). 점에 마우스를 올리면 값이 보인다.</p>
  <div class="legend"><span><i class="sw ours"></i>재현 (NSGA-II, seed 10개 합집합)</span><span><i class="sw paper sq"></i>논문 PF*</span></div>
  <div class="figs">{"".join(charts)}</div>
  <div class="card"><table class="tbl">
    <thead><tr><th>인스턴스</th><th>논문 E1 → E2</th><th>재현 E1 → E2</th><th>재현 점 중 논문에 지배됨</th>
    <th>논문 RHA 50→300</th><th>재현 RHA 중앙값 50→300</th><th>infeasible</th><th>checker</th></tr></thead>
    <tbody>{"".join(rows)}</tbody></table></div>
  <h3>iteration별 지표 추이 (재현 중앙값 vs 논문 NSGA-II)</h3>
  <div class="trends">{"".join(f'<div class="card">{t}</div>' for t in trends)}</div>
  <ul class="notes">
    <li><strong>맞는 점</strong>: BK15 최소 makespan 471(seed 7/10), RHA 증가·DPF 감소 경향, BK50 DPF 규모와 front 점 수(7).</li>
    <li><strong>다른 점</strong>: BK50 makespan이 960 아래로 내려가지 못함(논문 E1 ≈ 934). 재현 PF*의 대부분이 논문 PF*에 지배됨.</li>
    <li><strong>주의</strong>: PDS·MSF·DPF·RHA 절대값은 PF*가 달라 비교 대상이 아님. 5종을 모두 돌린 뒤 재계산한다.</li>
  </ul>
</section>

<section>
  <h2>전체 할일 (docs/TODO.md에서 자동 생성)</h2>
  <p class="desc">(A) 팀 결정 6개는 모두 완료라 아래 표로 요약했다. 남은 항목이 있는 묶음은 펼쳐져 있다.</p>
  {"".join(todo_html)}
</section>

<section>
  <h2>확정된 모델링 결정 (A1–A6, 2026-11-26)</h2>
  <div class="card"><table class="tbl"><thead><tr><th>#</th><th>항목</th><th>결정</th></tr></thead><tbody>{dec_rows}</tbody></table></div>
</section>

<section>
  <h2>문서 바로가기</h2>
  <div class="links">{link_html}</div>
</section>
<footer>이 파일은 생성물이다. 직접 고치지 말고 <code>docs/TODO.md</code> 또는 <code>status/build-status.py</code>를 고친 뒤 다시 생성한다.</footer>
</div>
</body>
</html>
"""


CSS = """
.viz-root{color-scheme:light;--surface-0:#f6f6f4;--surface-1:#ffffff;--border:#e3e3e0;--text-primary:#191919;
--text-secondary:#666666;--grid:#ececec;--axis:#b5b5b5;--series-1:#257de0;--series-2:#f47230;
--done:#008a17;--mostly:#00b894;--partial:#f2a600;--todo:#c9c9c9;--accent:#257de0;--bar-ink:#191919}
@media (prefers-color-scheme:dark){.viz-root{color-scheme:dark;--surface-0:#121212;--surface-1:#1d1d1d;--border:#333;
--text-primary:#efefef;--text-secondary:#9c9c9c;--grid:#2c2c2c;--axis:#555;--series-1:#338ced;--series-2:#e76624;
--done:#0aac23;--mostly:#00a888;--partial:#d28e05;--todo:#555;--accent:#338ced;--bar-ink:#ffffff}}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-0)}
.viz-root{background:var(--surface-0);color:var(--text-primary);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR",sans-serif;
max-width:1120px;margin:0 auto;padding:40px 24px 64px}
header h1{font-size:30px;margin:4px 0 6px;letter-spacing:-.02em}
.eyebrow{color:var(--text-secondary);font-size:13px}
.lede{color:var(--text-secondary);margin:0;font-size:13px}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;background:color-mix(in srgb,var(--text-primary) 7%,transparent);padding:1px 5px;border-radius:4px}
section{margin-top:40px}
h2{font-size:19px;margin:0 0 6px;letter-spacing:-.01em}
h3{font-size:15px;margin:24px 0 8px;color:var(--text-secondary);font-weight:600}
.desc{color:var(--text-secondary);margin:0 0 14px;font-size:14px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:24px}
.kpi{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:16px}
.kpi-v{font-size:26px;font-weight:700;letter-spacing:-.02em}
.kpi-l{color:var(--text-secondary);font-size:13px}
svg{width:100%;height:auto;display:block}
.grid{stroke:var(--grid);stroke-width:1}
.axis{stroke:var(--axis);stroke-width:1}
.tick{fill:var(--text-secondary);font-size:11px}
.axlabel{fill:var(--text-secondary);font-size:12px}
.rowlabel{fill:var(--text-primary);font-size:13px;font-weight:600}
.charttitle{fill:var(--text-primary);font-size:12px;font-weight:600}
.bar{stroke:var(--surface-1);stroke-width:2}
.bar.done{fill:var(--done)}.bar.mostly{fill:var(--mostly)}.bar.partial{fill:var(--partial)}.bar.todo{fill:var(--todo)}
.barlabel{fill:var(--bar-ink);font-size:11.5px;font-weight:600;pointer-events:none}
.barlabel.done{fill:#fff}
.today{stroke:var(--text-primary);stroke-width:2;stroke-dasharray:4 3}
.todaylabel{fill:var(--text-primary);font-size:12px;font-weight:600}
.line{fill:none;stroke-width:2}
.line.ours{stroke:var(--series-1)}.line.paper{stroke:var(--series-2);stroke-dasharray:5 4}
.pt{stroke:var(--surface-1);stroke-width:2;cursor:default}
.pt.ours{fill:var(--series-1)}.pt.paper{fill:var(--series-2)}
.pt:hover{stroke:var(--text-primary)}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--text-secondary);margin:10px 0}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px}
.sw.done{background:var(--done)}.sw.mostly{background:var(--mostly)}.sw.partial{background:var(--partial)}.sw.todo{background:var(--todo)}
.sw.ours{background:var(--series-1);border-radius:50%}.sw.paper{background:var(--series-2)}
.stages{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:14px}
.stage{background:var(--surface-1);border:1px solid var(--border);border-left:4px solid var(--todo);border-radius:10px;padding:12px 14px}
.stage.done{border-left-color:var(--done)}.stage.mostly{border-left-color:var(--mostly)}.stage.partial{border-left-color:var(--partial)}
.stage-h{display:flex;justify-content:space-between;align-items:center}
.stage-no{color:var(--text-secondary);font-size:12px}
.stage-name{font-weight:650;margin-top:6px}
.stage-meta{color:var(--text-secondary);font-size:12.5px}
.stage-note{font-size:13px;margin-top:6px}
.stage .prog{margin-top:8px}
.stage.current{box-shadow:0 0 0 2px var(--accent)}
.badge{font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:99px;border:1px solid var(--border)}
.badge.done::before,.badge.mostly::before,.badge.partial::before,.badge.todo::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:1px}
.badge.done::before{background:var(--done)}.badge.mostly::before{background:var(--mostly)}.badge.partial::before{background:var(--partial)}.badge.todo::before{background:var(--todo)}
.two{display:grid;grid-template-columns:1.5fr 1fr;gap:20px}
.tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.tbl th{text-align:left;color:var(--text-secondary);font-weight:600;font-size:12.5px;border-bottom:1px solid var(--border);padding:6px 8px}
.tbl td{border-bottom:1px solid var(--grid);padding:8px;vertical-align:top}
.tbl tr:last-child td{border-bottom:0}
.nowrap{white-space:nowrap}
.num{color:var(--text-secondary);font-variant-numeric:tabular-nums}
.sub{color:var(--text-secondary);font-size:12.5px;margin-top:2px}
.qlist{list-style:none;margin:0;padding:6px 16px}
.qlist li{padding:10px 0;border-bottom:1px solid var(--grid)}
.qlist li:last-child{border-bottom:0}
.tag{font-size:11.5px;font-weight:600;color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:0 6px;margin-right:8px}
.figs{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
figure{margin:0;background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
figcaption{font-weight:600;font-size:13.5px;margin-bottom:4px}
.trends{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.trends .card{padding:8px}
.notes{font-size:14px;padding-left:18px}
.notes li{margin:4px 0}
details.todo{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;margin-bottom:10px}
details.todo summary{display:flex;align-items:center;gap:12px;padding:12px 16px;cursor:pointer;list-style:none}
details.todo summary::-webkit-details-marker{display:none}
details.todo summary::before{content:"▸";color:var(--text-secondary);transition:transform .15s}
details.todo[open] summary::before{transform:rotate(90deg)}
.todo-title{font-weight:650;flex:1}
.prog{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.prog-bar{width:90px;height:6px;border-radius:99px;background:var(--grid);overflow:hidden}
.prog-bar span{display:block;height:100%;background:var(--done);border-radius:99px}
details.todo ul{list-style:none;margin:0;padding:0 16px 12px}
details.todo li{display:flex;gap:10px;padding:7px 0;border-top:1px solid var(--grid);font-size:14px}
details.todo li.done{color:var(--text-secondary)}
.box{flex:none;width:16px;height:16px;border-radius:4px;border:1.5px solid var(--axis);display:inline-flex;align-items:center;justify-content:center;font-size:11px;margin-top:3px}
li.done .box{background:var(--done);border-color:var(--done);color:#fff}
.sr{position:absolute;left:-9999px}
.links{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.links a{display:block;background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:10px 14px;color:var(--text-primary);text-decoration:none;font-weight:600;font-size:14px}
.links a:hover{border-color:var(--accent)}
.links a span{display:block;font-weight:400;font-size:12px;color:var(--text-secondary)}
footer{margin-top:40px;color:var(--text-secondary);font-size:12.5px}
@media (max-width:820px){.kpis,.trends{grid-template-columns:repeat(2,1fr)}.stages,.links{grid-template-columns:1fr 1fr}.two,.figs{grid-template-columns:1fr}}
"""

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"saved -> {OUT}")
