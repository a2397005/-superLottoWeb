"""
威力彩開獎資料爬蟲
資料來源：台灣彩券官網 https://www.taiwanlottery.com
執行後會將結果寫入 data/draws.json
"""

import json, time, re, os
from datetime import date
from pathlib import Path
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.taiwanlottery.com/",
}

OUTPUT = Path(__file__).parent.parent / "data" / "draws.json"

def fetch_draws(months=2):
    all_draws = []
    today = date.today()
    for i in range(months):
        m = (today.month - i - 1) % 12 + 1
        y = today.year - ((today.month - i - 1) // 12)
        tw_y = y - 1911
        url = "https://www.taiwanlottery.com/lotto/result/super_lotto638"
        params = {
            "srqtype": "1",
            "srdate": f"{tw_y:03d}{m:02d}",
        }
        print(f"[fetch] {y}/{m:02d} ...")
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            draws = parse(r.text)
            print(f"  → {len(draws)} 期")
            all_draws.extend(draws)
        except Exception as e:
            print(f"  → 失敗: {e}")
        time.sleep(2)
    return all_draws

def parse(html):
    draws = []
    # 找所有期別區塊
    blocks = re.findall(
        r'期別.*?(\d{9}).*?開獎日期.*?(\d{3}/\d{2}/\d{2}).*?'
        r'第一區([\d\s,，、]+?)第二區.*?(\d)',
        html, re.S
    )
    for b in blocks:
        try:
            period = int(b[0])
            raw_date = b[1].strip()
            y = int(raw_date.split('/')[0]) + 1911
            m, d = raw_date.split('/')[1], raw_date.split('/')[2]
            draw_date = f"{y}-{m}-{d}"
            nums = [int(x) for x in re.findall(r'\d+', b[2]) if 1 <= int(x) <= 38]
            z1 = sorted(nums[:6])
            z2 = int(b[3])
            if len(z1) == 6 and 1 <= z2 <= 8:
                draws.append({"period": period, "date": draw_date, "z1": z1, "z2": z2, "jackpot": 0})
        except Exception as e:
            print(f"  解析失敗: {e}")
    return draws

def merge(new):
    existing = []
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding='utf-8')).get('draws', [])
        except:
            pass
    m = {d['period']: d for d in existing}
    for d in new:
        m[d['period']] = d
    return sorted(m.values(), key=lambda x: x['period'], reverse=True)

if __name__ == '__main__':
    months = int(os.environ.get('CRAWL_MONTHS', '2'))
    new = fetch_draws(months)
    if new:
        all_draws = merge(new)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({
            "updated_at": __import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            "total": len(all_draws),
            "draws": all_draws
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"完成，共 {len(all_draws)} 期")
    else:
        print("未取得資料")
