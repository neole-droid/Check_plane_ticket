"""
대한항공 / 아시아나 마일리지(보너스) 항공권 대시보드 — 초안 v0.1

동작 방식
  1) collect : 실제 브라우저(Playwright)를 띄우고, 사용자가 직접 로그인/검색하면
               사이트가 내부적으로 받는 JSON 응답을 가로채 저장 (반자동)
  2) build   : 저장된 데이터로 dashboard.html 생성 (달력 + 가능 날짜 목록)
  3) demo    : 샘플 데이터로 대시보드 미리보기

설치
  pip install playwright
  playwright install chromium

실행 예
  python award_dashboard.py demo        # 대시보드 모양 먼저 확인
  python award_dashboard.py collect KE  # 대한항공 수집
  python award_dashboard.py collect OZ  # 아시아나 수집
  python award_dashboard.py build

※ [TODO] 표시는 DevTools로 실제 사이트를 확인한 뒤 채워야 하는 부분입니다.
"""

import json
import random
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "awards.json"
RAW_DIR = BASE / "data" / "raw"
PROFILE_DIR = BASE / "browser_profile"   # 로그인 세션 유지용 (비밀번호는 저장하지 않음)
OUT_HTML = BASE / "index.html"   # GitHub Pages 기본 페이지

AIRLINES = {
    "KE": {
        "name": "대한항공",
        "start_url": "https://www.koreanair.com/",
        # [TODO] DevTools > Network > Fetch/XHR 에서 보너스 좌석 검색 시
        #        호출되는 API URL을 확인해 아래 패턴을 수정하세요. (현재는 추정치)
        "response_pattern": re.compile(r"koreanair\.com/.*(award|bonus|availability)", re.I),
    },
    "OZ": {
        "name": "아시아나",
        "start_url": "https://flyasiana.com/",
        # [TODO] 위와 동일. 12월 법인 통합 이후 URL/구조가 바뀔 수 있음
        "response_pattern": re.compile(r"flyasiana\.com/.*(award|bonus|availability)", re.I),
    },
}


# ---------------------------------------------------------------------------
# 1. 수집 (반자동: 사람이 검색, 스크립트는 응답만 저장)
# ---------------------------------------------------------------------------
def collect(airline: str) -> None:
    from playwright.sync_api import sync_playwright

    cfg = AIRLINES[airline]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    captured = []

    def on_response(resp):
        if not cfg["response_pattern"].search(resp.url):
            return
        if "json" not in (resp.headers.get("content-type") or ""):
            return
        try:
            body = resp.json()
        except Exception:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        raw_path = RAW_DIR / f"{airline}_{stamp}.json"
        raw_path.write_text(json.dumps({"url": resp.url, "body": body},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        captured.append(body)
        print(f"  [저장] {raw_path.name}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR / airline), headless=False, locale="ko-KR")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_response)
        page.goto(cfg["start_url"])
        print(f"\n[{cfg['name']}] 브라우저에서 로그인 후 마일리지 항공권을 검색하세요.")
        print("검색이 끝나면 여기서 Enter를 누르세요.")
        input()
        ctx.close()

    records = []
    for body in captured:
        records.extend(parse_response(airline, body))
    merge_records(records)
    print(f"파싱된 좌석 정보 {len(records)}건 → {DATA_FILE}")


def parse_response(airline: str, body: dict) -> list:
    """
    [TODO] 핵심 작업: data/raw/*.json 을 열어 실제 구조를 보고 매핑을 작성.
    반환 형식(레코드 1건 = 날짜·구간·좌석등급 1개):
      {"airline": "KE", "origin": "ICN", "dest": "JFK", "date": "2026-12-20",
       "cabin": "C", "seats": 2, "miles": 62500, "flight": "KE081"}
    cabin: Y=일반석, C=비즈니스(프레스티지), F=일등석
    """
    records = []
    # 예시 골격 — 실제 키 이름으로 바꿔야 합니다.
    # for item in body.get("flights", []):
    #     for cls in item.get("classes", []):
    #         if cls.get("available"):
    #             records.append({
    #                 "airline": airline,
    #                 "origin": item["dep"], "dest": item["arr"],
    #                 "date": item["depDate"][:10],
    #                 "cabin": {"ECONOMY": "Y", "PRESTIGE": "C", "BUSINESS": "C",
    #                           "FIRST": "F"}.get(cls["name"], "Y"),
    #                 "seats": cls.get("seatCount"),
    #                 "miles": cls.get("mileage"),
    #                 "flight": item.get("flightNo"),
    #             })
    return records


def merge_records(new: list) -> None:
    """같은 (항공사·구간·날짜·등급·편명)은 최신 값으로 덮어씀."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []
    now = datetime.now().isoformat(timespec="minutes")
    key = lambda r: (r["airline"], r["origin"], r["dest"], r["date"], r["cabin"], r.get("flight"))
    merged = {key(r): r for r in old}
    for r in new:
        r["collected_at"] = now
        merged[key(r)] = r
    DATA_FILE.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=1),
                         encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. 대시보드 생성
# ---------------------------------------------------------------------------
def build(records=None) -> None:
    if records is None:
        records = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []
    html = DASHBOARD_TEMPLATE.replace("__DATA__", json.dumps(records, ensure_ascii=False))
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"대시보드 생성 → {OUT_HTML}  (브라우저로 여세요)")


def demo() -> None:
    random.seed(7)
    routes = [("ICN", "JFK"), ("ICN", "LAX"), ("ICN", "CDG"), ("ICN", "NRT")]
    miles = {"Y": 35000, "C": 62500, "F": 80000}
    recs, start = [], date.today()
    for o, d in routes:
        for i in range(0, 90):
            day = (start + timedelta(days=i)).isoformat()
            for al in ("KE", "OZ"):
                for cabin in ("Y", "C", "F"):
                    if cabin == "F" and al == "OZ":
                        continue
                    if random.random() < {"Y": 0.45, "C": 0.18, "F": 0.07}[cabin]:
                        recs.append({"airline": al, "origin": o, "dest": d, "date": day,
                                     "cabin": cabin, "seats": random.randint(1, 4),
                                     "miles": miles[cabin], "flight": f"{al}0{random.randint(10, 99)}",
                                     "collected_at": datetime.now().isoformat(timespec="minutes")})
    build(recs)


DASHBOARD_TEMPLATE = r"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>마일리지 좌석 대시보드</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#f5f7fa;--surface:#fff;--ink:#1c2430;--muted:#6b7684;--line:#dfe4ea;
 --ke:#1f6fb2;--oz:#a8323e;--empty:#eef1f4;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#12161c;--surface:#1a2029;--ink:#e6eaf0;
 --muted:#8b95a3;--line:#2b333f;--ke:#5aa4e0;--oz:#e06a76;--empty:#222a35;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#12161c;--surface:#1a2029;--ink:#e6eaf0;--muted:#8b95a3;--line:#2b333f;--ke:#5aa4e0;--oz:#e06a76;--empty:#222a35;color-scheme:dark}
:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.5 "IBM Plex Sans KR",system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:20px 16px 60px}
h1{font-size:1.4rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 18px}
.controls{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
select,button{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:6px;
 background:var(--surface);color:var(--ink)}
button{cursor:pointer}
button:focus-visible,select:focus-visible{outline:2px solid var(--ke);outline-offset:2px}
.legend{display:flex;gap:14px;color:var(--muted);font-size:.85rem;margin-bottom:10px}
.dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.month{display:flex;align-items:center;gap:10px;margin:8px 0}
.month h2{font-size:1.1rem;margin:0;min-width:110px;text-align:center}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.dow{font-size:.75rem;color:var(--muted);text-align:center}
.day{background:var(--surface);border:1px solid var(--line);border-radius:6px;min-height:68px;
 padding:4px;font-size:.75rem;cursor:pointer;text-align:left}
.day.off{visibility:hidden}
.day.sel{border-color:var(--ink)}
.day .n{font-weight:600}
.row{display:flex;gap:2px;margin-top:3px}
.chip{flex:1;height:14px;border-radius:2px;background:var(--empty);font-size:.65rem;
 line-height:14px;text-align:center;color:transparent}
.chip.on.KE{background:var(--ke);color:#fff}.chip.on.OZ{background:var(--oz);color:#fff}
table{width:100%;border-collapse:collapse;margin-top:18px;background:var(--surface)}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:.85rem}
th{color:var(--muted);font-weight:600}
.wrap{overflow-x:auto}
.empty{color:var(--muted);padding:24px 0}
</style></head><body><main>
<h1>마일리지 좌석 현황</h1>
<p class="sub" id="meta"></p>
<div class="controls">
 <select id="route" aria-label="구간"></select>
 <select id="cabin" aria-label="좌석 등급">
  <option value="ALL">전체 등급</option><option value="Y">일반석</option>
  <option value="C">비즈니스</option><option value="F">일등석</option></select>
 <select id="airline" aria-label="항공사">
  <option value="ALL">두 항공사</option><option value="KE">대한항공</option>
  <option value="OZ">아시아나</option></select>
</div>
<div class="legend"><span><span class="dot" style="background:var(--ke)"></span>대한항공</span>
 <span><span class="dot" style="background:var(--oz)"></span>아시아나</span>
 <span>칸: 일반 · 비즈 · 일등</span></div>
<div class="month"><button id="prev" aria-label="이전 달">‹</button><h2 id="ym"></h2>
 <button id="next" aria-label="다음 달">›</button></div>
<div class="grid" id="grid"></div>
<div class="wrap"><table id="list"></table></div>
</main>
<script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const CAB = {Y:"일반석",C:"비즈니스",F:"일등석"}, AL = {KE:"대한항공",OZ:"아시아나"};
let view = new Date(); view.setDate(1); let selDay = null;

const routes = [...new Set(DATA.map(r => r.origin + "-" + r.dest))].sort();
$("route").innerHTML = routes.map(r => `<option>${r}</option>`).join("");
const last = DATA.map(r => r.collected_at).sort().pop();
$("meta").textContent = DATA.length
  ? `${DATA.length}건 · 마지막 수집 ${last ? last.replace("T"," ") : "-"} · 수집 시점 기준이며 실제 잔여석은 사이트에서 다시 확인하세요`
  : "아직 데이터가 없습니다. collect 명령으로 먼저 수집하세요.";

function filtered(){
  const [o,d] = ($("route").value||"-").split("-"), c = $("cabin").value, a = $("airline").value;
  return DATA.filter(r => r.origin===o && r.dest===d &&
    (c==="ALL"||r.cabin===c) && (a==="ALL"||r.airline===a));
}
const ymd = dt => dt.toISOString().slice(0,10);

function render(){
  const rows = filtered(), byDay = {};
  rows.forEach(r => (byDay[r.date] ??= []).push(r));
  const y = view.getFullYear(), m = view.getMonth();
  $("ym").textContent = `${y}년 ${m+1}월`;
  const first = new Date(Date.UTC(y,m,1)).getUTCDay(), days = new Date(y,m+1,0).getDate();
  let h = "일월화수목금토".split("").map(d => `<div class="dow">${d}</div>`).join("");
  for(let i=0;i<first;i++) h += `<div class="day off"></div>`;
  for(let d=1; d<=days; d++){
    const key = ymd(new Date(Date.UTC(y,m,d))), list = byDay[key]||[];
    const lane = al => `<div class="row">${["Y","C","F"].map(c => {
      const hit = list.find(r => r.airline===al && r.cabin===c);
      return `<span class="chip ${al} ${hit?"on":""}" title="${AL[al]} ${CAB[c]}">${hit?(hit.seats??"✓"):""}</span>`;
    }).join("")}</div>`;
    h += `<button class="day ${key===selDay?"sel":""}" data-d="${key}">
      <span class="n">${d}</span>${lane("KE")}${lane("OZ")}</button>`;
  }
  $("grid").innerHTML = h;
  $("grid").querySelectorAll(".day[data-d]").forEach(b =>
    b.onclick = () => { selDay = selDay===b.dataset.d ? null : b.dataset.d; render(); });

  const shown = (selDay ? (byDay[selDay]||[]) : rows).slice()
    .sort((a,b) => a.date.localeCompare(b.date) || a.airline.localeCompare(b.airline));
  $("list").innerHTML = shown.length
    ? `<tr><th>날짜</th><th>항공사</th><th>편명</th><th>등급</th><th>잔여</th><th>마일</th></tr>` +
      shown.map(r => `<tr><td>${r.date}</td><td>${AL[r.airline]}</td><td>${r.flight??"-"}</td>
        <td>${CAB[r.cabin]}</td><td>${r.seats??"-"}</td><td>${r.miles?.toLocaleString()??"-"}</td></tr>`).join("")
    : `<tr><td class="empty">조건에 맞는 좌석이 없습니다. 등급이나 항공사 필터를 넓혀 보세요.</td></tr>`;
}
["route","cabin","airline"].forEach(id => $(id).onchange = () => { selDay=null; render(); });
$("prev").onclick = () => { view.setMonth(view.getMonth()-1); render(); };
$("next").onclick = () => { view.setMonth(view.getMonth()+1); render(); };
render();
</script></body></html>"""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd == "collect":
        collect(sys.argv[2].upper() if len(sys.argv) > 2 else "KE")
    elif cmd == "build":
        build()
    else:
        demo()
