"""
威力彩開獎資料爬蟲
資料來源：台灣彩券官網 https://www.taiwanlottery.com
執行後會將結果寫入 data/draws.json
"""
import json, os
from datetime import datetime, date
from pathlib import Path
from TaiwanLottery import TaiwanLotteryCrawler

OUTPUT = Path(__file__).parent.parent / "data" / "draws.json"

def to_record(item):
    """把套件回傳的格式轉成我們網站要用的格式"""
    period = int(item["期別"])
    raw_date = item["開獎日期"]  # 例如 "2026-06-23T00:00:00.000Z" 或 "115/06/23"
    try:
        d = raw_date.split("T")[0]
    except Exception:
        d = raw_date

    z1 = sorted(item["第一區"])
    z2 = item["第二區"][0] if isinstance(item["第二區"], list) else item["第二區"]

    return {
        "period": period,
        "date": d,
        "z1": z1,
        "z2": int(z2),
        "jackpot": 0
    }

def fetch_recent_months(months=2):
    lottery = TaiwanLotteryCrawler()
    today = date.today()
    all_items = []
    for i in range(months):
        m = (today.month - i - 1) % 12 + 1
        y = today.year - ((today.month - i - 1) // 12)
        try:
            result = lottery.super_lotto([str(y), f"{m:02d}"])
            print(f"{y}-{m:02d} 取得 {len(result)} 筆")
            all_items.extend(result)
        except Exception as e:
            print(f"{y}-{m:02d} 失敗: {e}")
    return all_items

def merge(new_records):
    existing = []
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8")).get("draws", [])
        except Exception:
            pass
    m = {r["period"]: r for r in existing}
    for r in new_records:
        m[r["period"]] = r
    return sorted(m.values(), key=lambda x: x["period"], reverse=True)

if __name__ == "__main__":
    months = int(os.environ.get("CRAWL_MONTHS", "2"))
    raw_items = fetch_recent_months(months)
    records = []
    for item in raw_items:
        try:
            records.append(to_record(item))
        except Exception as e:
            print(f"轉換失敗: {e} / 原始資料: {item}")

    if records:
        merged = merge(records)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({
            "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(merged),
            "draws": merged
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"完成，共 {len(merged)} 期")
    else:
        print("未取得任何資料")
