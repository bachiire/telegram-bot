import asyncio
import json
import websockets
import requests
import time
import os
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
# ==========================================
BOT_TOKEN = "8893923436:AAFzB8HuilhGoPrUfvhgbpf931D_zZ0eaqo"
CHAT_IDS = ["829280637", "5232339352"]
# ==========================================

FONT_PATH = "Roboto.ttf"
latest_data_list = []
active_trades = {} # قاموس لتتبع الصفقات المفتوحة حالياً

def get_font(size=14):
    try:
        if not os.path.exists(FONT_PATH):
            url = "https://github.com/matomo-org/travis-scripts/raw/master/fonts/Roboto-Regular.ttf"
            urllib.request.urlretrieve(url, FONT_PATH)
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def broadcast_telegram_msg(text):
    """إرسال رسالة تنبيه لجميع الحسابات المحددة في القائمة"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=5)
        except Exception as e:
            print(f"خطأ في إرسال الرسالة لـ {chat_id}: {e}")

def get_full_historical_data(symbol):
    data = {}
    try:
        res_1h = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=2").json()
        if len(res_1h) >= 2:
            prev_1h = res_1h[0]
            op_1h, cl_1h = float(prev_1h[1]), float(prev_1h[4])
            vol_1h, tr_1h = float(prev_1h[7]), int(prev_1h[8])
            data['1h_price_chg'] = ((cl_1h - op_1h) / op_1h * 100) if op_1h else 0
            data['1h_avg_tps'] = tr_1h / 3600
            data['1h_avg_ats'] = vol_1h / tr_1h if tr_1h else 0
            data['last_price'] = cl_1h 
            
        res_4h = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=3").json()
        if len(res_4h) >= 3:
            prev_4h, older_4h = res_4h[1], res_4h[0]
            op_4h, cl_4h = float(prev_4h[1]), float(prev_4h[4])
            vol_4h, tr_4h = float(prev_4h[7]), int(prev_4h[8])
            older_vol_4h = float(older_4h[7])
            
            data['4h_vol'] = vol_4h
            data['4h_vol_chg'] = ((vol_4h - older_vol_4h) / older_vol_4h * 100) if older_vol_4h else 0
            data['4h_price_chg'] = ((cl_4h - op_4h) / op_4h * 100) if op_4h else 0
            data['4h_avg_tps'] = tr_4h / 14400
            data['4h_avg_ats'] = vol_4h / tr_4h if tr_4h else 0
    except:
        pass
    
    for k in ['1h_price_chg', '1h_avg_tps', '1h_avg_ats', '4h_vol', '4h_vol_chg', '4h_price_chg', '4h_avg_tps', '4h_avg_ats', 'last_price']:
        data.setdefault(k, 0.001) 
    return data

async def setup_market_data():
    print("⏳ جاري مسح السوق وتحديث قائمة العملات الأنشط...")
    data = await asyncio.to_thread(requests.get, "https://api.binance.com/api/v3/ticker/24hr")
    data = data.json()
    
    exclude = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT"]
    valid_coins = [c for c in data if c['symbol'].endswith("USDT") and c['symbol'] not in exclude]
    
    valid_coins.sort(key=lambda x: int(x['count']), reverse=True)
    temp_symbols = [c['symbol'] for c in valid_coins[:120]]
    
    async def fetch_data(sym):
        result = await asyncio.to_thread(get_full_historical_data, sym)
        return sym, result

    tasks = [fetch_data(sym) for sym in temp_symbols]
    results = await asyncio.gather(*tasks)
    
    db = {sym: res for sym, res in results if res}
    top_symbols = sorted(db.keys(), key=lambda s: db[s]['1h_price_chg'], reverse=True)[:15]
    
    print(f"✅ تم تحديث القائمة بأقوى {len(top_symbols)} عملة صعوداً حالياً.")
    return top_symbols, db

def draw_and_send_table(data_list):
    if not data_list: return
        
    headers = ["SYMBOL", "4HR VOL", "4H V.CHG%", "CLOSE", "TPS", "1H AVG TPS", "1H TPS CHG%", "1H P.CHG%", "4H TPS CHG%", "4H P.CHG%", "ATS", "1H ATS CHG%", "4H ATS CHG%"]
    col_widths = [110, 95, 95, 85, 55, 95, 105, 95, 105, 95, 60, 105, 105]
    
    row_height = 35
    width = sum(col_widths) + 20
    height = row_height * (len(data_list) + 1) + 20

    img = Image.new('RGB', (width, height), color=(15, 15, 20))
    draw = ImageDraw.Draw(img)
    font = get_font(13)
    
    draw.rectangle([10, 10, width-10, 10+row_height], fill=(15, 30, 100))
    
    x_off = 15
    for i, h in enumerate(headers):
        draw.text((x_off, 20), h, fill=(200, 220, 255), font=font)
        x_off += col_widths[i]

    y_off = 10 + row_height
    for i, row in enumerate(data_list):
        bg = (22, 23, 28) if i % 2 == 0 else (15, 15, 20)
        draw.rectangle([10, y_off, width-10, y_off+row_height], fill=bg)
        
        def get_color(val): return (100, 255, 100) if val > 0 else (255, 80, 80)
        
        cols_data = [
            (row['sym'], (255, 255, 255)),
            (f"${row['4h_vol']/1000000:.1f}M", (200, 200, 200)),
            (f"{row['4h_vol_chg']:+.1f}%", get_color(row['4h_vol_chg'])),
            (f"{row['price']:.4f}", (150, 255, 200)),
            (str(row['tps']), (255, 255, 255)),
            (f"{row['1h_avg_tps']:.2f}", (200, 200, 200)),
            (f"{row['1h_tps_chg']:+.1f}%", get_color(row['1h_tps_chg'])),
            (f"{row['1h_price_chg']:+.2f}%", get_color(row['1h_price_chg'])),
            (f"{row['4h_tps_chg']:+.1f}%", get_color(row['4h_tps_chg'])),
            (f"{row['4h_price_chg']:+.1f}%", get_color(row['4h_price_chg'])),
            (f"{row['ats']:.0f}", (255, 255, 255)),
            (f"{row['1h_ats_chg']:+.1f}%", get_color(row['1h_ats_chg'])),
            (f"{row['4h_ats_chg']:+.1f}%", get_color(row['4h_ats_chg']))
        ]
        
        x_c = 15
        for idx, (text, color) in enumerate(cols_data):
            draw.text((x_c, y_off + 8), text, fill=color, font=font)
            x_c += col_widths[idx]
            
        draw.line([10, y_off+row_height, width-10, y_off+row_height], fill=(30, 30, 40), width=1)
        y_off += row_height

    bio = io.BytesIO()
    img.save(bio, format='PNG')
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    print("⏳ جاري إرسال الجدول المحدث للحسابات...")
    
    for chat_id in CHAT_IDS:
        bio.seek(0) 
        try:
            requests.post(url, files={'photo': ('dashboard.png', bio, 'image/png')}, data={'chat_id': chat_id})
            print(f"✅ تم إرسال الصورة المحدثة للحساب: {chat_id}")
        except Exception as e:
            print(f"❌ خطأ في الإرسال للحساب {chat_id}: {e}")

async def run_advanced_dashboard():
    global latest_data_list, active_trades
    
    while True:
        try:
            top_symbols, history_db = await setup_market_data()
            
            streams = "/".join([f"{sym.lower()}@ticker/{sym.lower()}@trade" for sym in top_symbols])
            url = f"wss://stream.binance.com:9443/stream?streams={streams}"
            
            live_metrics = {}
            for sym in top_symbols:
                live_metrics[sym] = {'tps_count': 0, 'vol_sum': 0.0, 'price': history_db[sym]['last_price']}
                
            last_update = time.time()
            session_start = time.time()
            
            async with websockets.connect(url, max_size=None) as ws:
                print("✅ متصل بالبث اللحظي. الجدول يتحدث تلقائياً كل ثانية ويُجدد العملات كل 5 دقائق.")
                while True:
                    # إعادة فحص السوق بالكامل وتغيير العملات كل 5 دقائق (300 ثانية) لتكون متجددة دائماً
                    if time.time() - session_start > 300:
                        print("🔄 إعادة سحب العملات الأنشط بناءً على وضع السوق الحالي...")
                        break
                        
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(response)
                        
                        if 'data' in data:
                            stream_data = data['data']
                            event = stream_data.get('e')
                            sym = stream_data.get('s')
                            
                            if sym in live_metrics:
                                if event == 'trade':
                                    live_metrics[sym]['tps_count'] += 1
                                    live_metrics[sym]['vol_sum'] += (float(stream_data['p']) * float(stream_data['q']))
                                elif event == '24hrTicker':
                                    curr_price = float(stream_data['c'])
                                    live_metrics[sym]['price'] = curr_price
                                    
                                    # تتبع الأهداف ووقف الخسارة
                                    if sym in active_trades:
                                        trade = active_trades[sym]
                                        if curr_price <= trade['sl']:
                                            msg = f"🛑 *ضرب وقف الخسارة (STOP LOSS)*\nالعملة: `{sym}`\nالسعر الحالي: `{curr_price}`"
                                            broadcast_telegram_msg(msg)
                                            del active_trades[sym]
                                        elif curr_price >= trade['tp2']:
                                            msg = f"🏆 *تم تحقيق الهدف الثاني بنجاح! (TP2)* 🚀\nالعملة: `{sym}`\nالسعر الحالي: `{curr_price}`"
                                            broadcast_telegram_msg(msg)
                                            del active_trades[sym]
                                        elif curr_price >= trade['tp1'] and not trade['tp1_hit']:
                                            msg = f"🎯 *تم تحقيق الهدف الأول! (TP1)* ✅\nالعملة: `{sym}`\nالسعر الحالي: `{curr_price}`\n_يُصح بتحريك وقف الخسارة لنقطة الدخول._"
                                            broadcast_telegram_msg(msg)
                                            active_trades[sym]['tp1_hit'] = True
                    except asyncio.TimeoutError:
                        pass # مرور ثانية واحدة، يتم تحديث البيانات وعرض الجدول
                    
                    now = time.time()
                    if now - last_update >= 1.0:
                        last_update = now
                        current_list = []
                        
                        for sym in top_symbols:
                            if sym not in live_metrics: continue
                            hist = history_db[sym]
                            metrics = live_metrics[sym]
                            
                            tps = metrics['tps_count']
                            vol_sum = metrics['vol_sum']
                            ats = (vol_sum / tps) if tps > 0 else 0
                            price = metrics['price']
                            
                            metrics['tps_count'] = 0
                            metrics['vol_sum'] = 0.0
                            
                            avg_1h_tps, avg_4h_tps = hist['1h_avg_tps'], hist['4h_avg_tps']
                            avg_1h_ats, avg_4h_ats = hist['1h_avg_ats'], hist['4h_avg_ats']
                            
                            row_data = {
                                'sym': sym, 'price': price, '4h_vol': hist['4h_vol'], '4h_vol_chg': hist['4h_vol_chg'],
                                'tps': tps, '1h_avg_tps': avg_1h_tps, 
                                '1h_tps_chg': ((tps - avg_1h_tps)/avg_1h_tps*100) if avg_1h_tps else 0,
                                '4h_tps_chg': ((tps - avg_4h_tps)/avg_4h_tps*100) if avg_4h_tps else 0,
                                '1h_price_chg': hist['1h_price_chg'], '4h_price_chg': hist['4h_price_chg'],
                                'ats': ats, 
                                '1h_ats_chg': ((ats - avg_1h_ats)/avg_1h_ats*100) if avg_1h_ats else 0, 
                                '4h_ats_chg': ((ats - avg_4h_ats)/avg_4h_ats*100) if avg_4h_ats else 0
                            }
                            current_list.append(row_data)
                            
                            # شروط إرسال صفقة شراء جديدة بناءً على نظام السيولة المحسن
                            is_price_ok = row_data['1h_price_chg'] > 1.0
                            is_tps_surge = row_data['1h_tps_chg'] > 30.0
                            is_ats_expansion = row_data['1h_ats_chg'] > 0.0
                            
                            if is_price_ok and is_tps_surge and is_ats_expansion and sym not in active_trades and len(active_trades) < 20:
                                stop_loss = price * 0.96
                                target_1 = price * 1.06
                                target_2 = price * 1.12
                                
                                signal_text = (
                                    f"🚨 *تنبيه صفقة سيولة مؤكدة (BUY SIGNAL)* 🚨\n\n"
                                    f"💎 *العملة:* `{sym}`\n"
                                    f"💵 *سعر الدخول:* `{price}`\n"
                                    f"🎯 *الهدف الأول (TP1):* `{target_1:.4f}` (+6%)\n"
                                    f"🎯 *الهدف الثاني (TP2):* `{target_2:.4f}` (+12%)\n"
                                    f"🛑 *وقف الخسارة (SL):* `{stop_loss:.4f}` (-4%)\n\n"
                                    f"📊 *تأكيد السيولة اللحظية:*\n"
                                    f"• صعود الساعة: `{row_data['1h_price_chg']:+.2f}%`\n"
                                    f"• طفرة الصفقات: `{row_data['1h_tps_chg']:+.1f}%`\n"
                                    f"• نمو حجم الصفقة: `{row_data['1h_ats_chg']:+.1f}%`"
                                )
                                broadcast_telegram_msg(signal_text)
                                
                                active_trades[sym] = {
                                    'entry': price,
                                    'sl': stop_loss,
                                    'tp1': target_1,
                                    'tp2': target_2,
                                    'tp1_hit': False
                                }
                        
                        latest_data_list = current_list
        except Exception as e:
            print(f"خطأ في حلقة التشغيل، جاري إعادة المحاولة... {e}")
            await asyncio.sleep(5)

async def telegram_listener():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    last_update_id = 0
    while True:
        try:
            res = await asyncio.to_thread(requests.get, f"{url}?offset={last_update_id}", timeout=5)
            data = res.json()
            for item in data.get('result', []):
                last_update_id = item['update_id'] + 1
                if item.get('message', {}).get('text', '') == '/send':
                    print("\n📩 أمر /send مستلم! جاري إرسال أحدث صورة للجدول...")
                    await asyncio.to_thread(draw_and_send_table, latest_data_list)
        except: pass
        await asyncio.sleep(1)

async def main():
    await asyncio.gather(run_advanced_dashboard(), telegram_listener())

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
