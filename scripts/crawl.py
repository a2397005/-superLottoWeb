"""
威力彩開獎資料爬蟲
資料來源：台灣彩券官網 https://www.taiwanlottery.com
執行後會將結果寫入 data/draws.json
"""

import json
import time
import re
import os
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 設定 ───────────────────────────────────────────────────
BASE_URL = "https://www.taiwanlottery.com"
RESULT_URL = f"{BASE_URL}/lotto/result/super_lotto638"
HISTORY_URL = f"{BASE_URL}/lotto/history/history_result/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "draws.json"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


# ── 工具函式 ───────────────────────────────────────────────
def tw_year_to_ad(tw_str: str) -> str:
    """民國年轉西元，例如 '115/06/23' → '2026-06-23'"""
    parts = re.split(r"[/\-]", tw_str.strip())
    if len(parts) == 3:
        ad = int(parts[0]) + 1911
        return f"{ad}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return tw_str


def safe_int(s: str) -> int:
    try:
        return int(re.sub(r"[^\d]", "", s))
    except Exception:
        return 0


def fetch(url: str, params: dict = None, retries: int = 3) -> requests.Response:
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"[fetch] 第 {i+1} 次失敗: {e}")
            time.sleep(3)
    raise RuntimeError(f"無法取得 {url}")


# ── 解析最新開獎（113年後使用新版頁面） ─────────────────────
def parse_latest_draws(html: str) -> list[dict]:
    """
    解析台彩「各期獎號及開獎結果」頁面 HTML
    每次查詢預設回傳最近數期資料
    """
    soup = BeautifulSoup(html, "html.parser")
    draws = []

    # 台彩新版頁面：每期資料包在 .result-item 或 table rows 裡
    # 因頁面結構可能異動，使用多種 selector 嘗試
    rows = (
        soup.select("table.result-table tbody tr")
        or soup.select(".draw-result")
        or soup.select("[data-period]")
    )

    if not rows:
        # fallback: 直接解析文字
        print("[parse] 找不到標準 selector，嘗試文字解析")
        return _parse_by_text(soup)

    for row in rows:
        try:
            draw = _parse_row(row)
            if draw:
                draws.append(draw)
        except Exception as e:
            print(f"[parse] 解析列失敗: {e}")

    return draws


def _parse_row(tag) -> dict | None:
    text = tag.get_text(" ", strip=True)
    # 期別
    period_m = re.search(r"(\d{9})", text)
    if not period_m:
        return None
    period = int(period_m.group(1))

    # 日期
    date_m = re.search(r"(\d{3}/\d{2}/\d{2})", text)
    draw_date = tw_year_to_ad(date_m.group(1)) if date_m else ""

    # 號碼（第一區：紅球，第二區：藍球）
    nums = re.findall(r"\b(\d{1,2})\b", text)
    # 過濾掉期別數字後的號碼
    z1, z2 = [], None
    for n in nums:
        n = int(n)
        if 1 <= n <= 38 and len(z1) < 6:
            z1.append(n)
        elif 1 <= n <= 8 and z2 is None and len(z1) == 6:
            z2 = n

    if len(z1) != 6 or z2 is None:
        return None

    return {
        "period": period,
        "date": draw_date,
        "z1": sorted(z1),
        "z2": z2,
    }


def _parse_by_text(soup: BeautifulSoup) -> list[dict]:
    """備用：從頁面全文用正規表達式抽取開獎資料"""
    text = soup.get_text(" ")
    # 期別格式 1150000XX
    blocks = re.split(r"(\d{9})", text)
    draws = []
    for i in range(1, len(blocks), 2):
        try:
            period = int(blocks[i])
            chunk = blocks[i + 1] if i + 1 < len(blocks) else ""
            date_m = re.search(r"(\d{3}/\d{2}/\d{2})", chunk)
            draw_date = tw_year_to_ad(date_m.group(1)) if date_m else ""
            nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", chunk)]
            z1 = sorted([n for n in nums if 1 <= n <= 38])[:6]
            z2_candidates = [n for n in nums if 1 <= n <= 8]
            z2 = z2_candidates[0] if z2_candidates else None
            if len(z1) == 6 and z2:
                draws.append({"period": period, "date": draw_date, "z1": z1, "z2": z2})
        except Exception:
            continue
    return draws


# ── 主爬蟲：抓最近 N 個月 ─────────────────────────────────
def crawl_month(year: int, month: int) -> list[dict]:
    """抓指定年月的開獎資料"""
    # 台彩查詢參數格式（民國年）
    tw_year = year - 1911
    params = {
        "game": "super_lotto638",
        "from_date": f"{tw_year}/{month:02d}/01",
        "to_date": f"{tw_year}/{month:02d}/31",
    }
    print(f"[crawl] 抓取 {year}/{month:02d} ...")
    try:
        r = fetch(RESULT_URL, params=params)
        draws = parse_latest_draws(r.text)
        print(f"[crawl]   → 取得 {len(draws)} 期")
        return draws
    except Exception as e:
        print(f"[crawl] 失敗: {e}")
        return []


def crawl_recent(months: int = 3) -> list[dict]:
    """抓最近 N 個月資料"""
    all_draws = []
    today = date.today()
    for i in range(months):
        m = (today.month - i - 1) % 12 + 1
        y = today.year - ((today.month - i - 1) // 12)
        draws = crawl_month(y, m)
        all_draws.extend(draws)
        time.sleep(1.5)  # 禮貌性延遲

    # 去重 + 排序
    seen = set()
    unique = []
    for d in all_draws:
        if d["period"] not in seen:
            seen.add(d["period"])
            unique.append(d)

    return sorted(unique, key=lambda x: x["period"], reverse=True)


# ── 合併既有資料 ──────────────────────────────────────────
def merge_with_existing(new_draws: list[dict]) -> list[dict]:
    """將新資料與 data/draws.json 合併，避免重複"""
    existing = []
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, encoding="utf-8") as f:
                data = json.load(f)
                existing = data.get("draws", [])
        except Exception:
            pass

    existing_map = {d["period"]: d for d in existing}
    for d in new_draws:
        existing_map[d["period"]] = d  # 新資料覆蓋舊資料

    merged = sorted(existing_map.values(), key=lambda x: x["period"], reverse=True)
    return merged


# ── 寫出 JSON ──────────────────────────────────────────────
def write_json(draws: list[dict]):
    payload = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(draws),
        "draws": draws,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[write] 寫出 {len(draws)} 期資料 → {OUTPUT_PATH}")


# ── 入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== 威力彩爬蟲開始 ===")

    # 第一次執行抓 6 個月，之後日常只抓 2 個月
    months = int(os.environ.get("CRAWL_MONTHS", "2"))
    new_draws = crawl_recent(months=months)

    if new_draws:
        all_draws = merge_with_existing(new_draws)
        write_json(all_draws)
        print(f"=== 完成，共 {len(all_draws)} 期 ===")
    else:
        print("[main] 未取得任何資料，保留既有 JSON")
