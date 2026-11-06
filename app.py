import streamlit as st
import pandas as pd
import numpy as np
import requests
from streamlit_autorefresh import st_autorefresh

# =========================================================
# MAZONI BOT | Multi-Asset Smart Market Levels + Fibonacci
# تحليل الأصل الأساسي فقط، وليس عقود الخيارات.
# =========================================================

st.set_page_config(page_title="MAZONI BOT", page_icon="👑", layout="wide")
API_BASE = "https://biquote.io/api"
REFRESH_MS = 15000

ASSETS = {
    "SPX — S&P 500": "SPX",
    "SPY — S&P 500 ETF": "SPY",
    "AMZN — Amazon": "AMZN",
    "MSFT — Microsoft": "MSFT",
    "AAPL — Apple": "AAPL",
    "PEP — PepsiCo": "PEP",
    "GOOGL — Alphabet": "GOOGL",
    "META — Meta": "META",
}
st_autorefresh(interval=REFRESH_MS, key="mazoni_refresh")

st.markdown("""
<style>
.stApp{background:radial-gradient(circle at 15% 5%,rgba(191,151,65,.13),transparent 28%),linear-gradient(135deg,#07090d,#10131a 55%,#07090d);color:#f4f0e7}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#101319,#080a0e);border-right:1px solid rgba(201,166,92,.28)}
h1,h2,h3{color:#e3c477!important}
.mazoni-title{text-align:center;padding:10px 0 18px;color:#d7b568;font-size:38px;font-weight:900;letter-spacing:3px}
.mazoni-sub{text-align:center;color:#a9a39a;font-size:12px;letter-spacing:4px;margin-top:-14px;margin-bottom:24px}
.metric-card,.signal-card{background:linear-gradient(145deg,rgba(28,32,41,.96),rgba(12,15,21,.96));border:1px solid rgba(204,170,99,.30);border-radius:15px;padding:16px;min-height:94px}
.metric-label{color:#aaa49a;font-size:12px;margin-bottom:8px}
.metric-value{color:#f4e6c3;font-size:22px;font-weight:800}
.signal-card{padding:22px;margin:8px 0 16px}
.signal-call{color:#35d39a;font-size:30px;font-weight:900}
.signal-put{color:#ff6b75;font-size:30px;font-weight:900}
.signal-wait{color:#e3c477;font-size:30px;font-weight:900}
.small-note{color:#a9a39a;font-size:12px}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="mazoni-title">👑 MAZONI BOT</div>', unsafe_allow_html=True)
st.markdown('<div class="mazoni-sub">SMART MARKET LEVELS · FIBONACCI</div>', unsafe_allow_html=True)


# ---------------- DATA ----------------
@st.cache_data(ttl=8, show_spinner=False)
def get_json(url, params=None):
    response = requests.get(url, params=params, timeout=12,
                            headers={"User-Agent": "MAZONI-BOT/1.0"})
    response.raise_for_status()
    return response.json()


def get_quote(symbol):
    data = get_json(f"{API_BASE}/{symbol}")
    if isinstance(data, dict) and isinstance(data.get("quote"), dict):
        data = data["quote"]
    return data


def get_candles(symbol, interval, limit=250):
    data = get_json(f"{API_BASE}/{symbol}/ohlc",
                    params={"interval": interval, "limit": limit})
    bars = data.get("bars", []) if isinstance(data, dict) else data
    if not isinstance(bars, list) or not bars:
        raise ValueError(f"لا توجد شموع للفريم {interval}")
    df = pd.DataFrame(bars)
    required = ["openTime", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"حقول الشموع ناقصة: {', '.join(missing)}")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    parsed = pd.to_datetime(df["openTime"], utc=True, errors="coerce")
    if parsed.isna().all():
        raw = pd.to_numeric(df["openTime"], errors="coerce")
        valid = raw.dropna()
        if not valid.empty:
            parsed = pd.to_datetime(raw, unit="ms" if valid.median() > 10**11 else "s",
                                    utc=True, errors="coerce")
    df["time"] = parsed
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if "isOpen" in df:
        is_open = df["isOpen"].astype(str).str.lower().isin(["true", "1", "yes"])
        df = df.loc[~is_open].copy()
    if len(df) < 60:
        raise ValueError(f"البيانات غير كافية للفريم {interval}: {len(df)} شمعة")
    return df.reset_index(drop=True)


# ---------------- INDICATORS ----------------
def add_indicators(df):
    x = df.copy()
    x["ema20"] = x.close.ewm(span=20, adjust=False).mean()
    x["ema50"] = x.close.ewm(span=50, adjust=False).mean()
    delta = x.close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = ag / al.replace(0, np.nan)
    x["rsi"] = 100 - 100/(1+rs)
    x.loc[(al == 0) & (ag > 0), "rsi"] = 100
    x.loc[(ag == 0) & (al > 0), "rsi"] = 0
    prev = x.close.shift(1)
    tr = pd.concat([x.high-x.low, (x.high-prev).abs(), (x.low-prev).abs()], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    e12 = x.close.ewm(span=12, adjust=False).mean()
    e26 = x.close.ewm(span=26, adjust=False).mean()
    x["macd"] = e12-e26
    x["macd_signal"] = x.macd.ewm(span=9, adjust=False).mean()
    x["vol_avg20"] = x.volume.rolling(20).mean() if "volume" in x else np.nan
    return x


def trend(row):
    if row.close > row.ema20 > row.ema50:
        return "صاعد", 1
    if row.close < row.ema20 < row.ema50:
        return "هابط", -1
    return "عرضي", 0


def analyze(df):
    x = add_indicators(df)
    r = x.iloc[-1]
    name, value = trend(r)
    return {
        "df": x, "close": float(r.close), "ema20": float(r.ema20),
        "ema50": float(r.ema50), "rsi": float(r.rsi) if pd.notna(r.rsi) else np.nan,
        "atr": float(r.atr) if pd.notna(r.atr) else np.nan,
        "macd": float(r.macd), "macd_signal": float(r.macd_signal),
        "trend": name, "trend_value": value
    }


# ---------------- FIBONACCI + TRADE SCENARIOS ----------------
FIB_RATIOS = [0.236, 0.382, 0.500, 0.618, 0.786]


def swing_range(df, lookback=80):
    recent = df.tail(lookback)
    low_i, high_i = recent.low.idxmin(), recent.high.idxmax()
    low, high = float(recent.loc[low_i, "low"]), float(recent.loc[high_i, "high"])
    if not np.isfinite(low+high) or high <= low:
        raise ValueError("تعذر تحديد قمة وقاع صالحين لحساب فيبوناتشي")
    return low, high, low_i, high_i


def fib_levels(low, high, direction):
    span = high-low
    if direction == 1:  # موجة صاعدة: التصحيح محسوب نزولاً من القمة
        return {f"{r*100:.1f}%": high-span*r for r in FIB_RATIOS}
    # موجة هابطة: التصحيح محسوب صعوداً من القاع
    return {f"{r*100:.1f}%": low+span*r for r in FIB_RATIOS}


def make_scenario(direction, low, high, atr, price):
    """سيناريو مراقبة مبني على نطاق السوينغ، حتى عند عدم اكتمال الإشارة."""
    span = high-low
    if direction == 1:
        f50, f618 = high-span*.50, high-span*.618
        entry_low, entry_high = min(f50, f618), max(f50, f618)
        stop = low-0.25*atr
        risk = max(((entry_low+entry_high)/2)-stop, atr*.5)
        targets = [high, high+span*.272, high+span*.618]
        valid_side = "CALL"
        price_near = entry_low-0.25*atr <= price <= entry_high+0.25*atr
    else:
        f50, f618 = low+span*.50, low+span*.618
        entry_low, entry_high = min(f50, f618), max(f50, f618)
        stop = high+0.25*atr
        risk = max(stop-((entry_low+entry_high)/2), atr*.5)
        targets = [low, low-span*.272, low-span*.618]
        valid_side = "PUT"
        price_near = entry_low-0.25*atr <= price <= entry_high+0.25*atr

    # لا نعرض دخولاً قابلاً للتنفيذ إذا ابتعد السعر كثيراً عن المنطقة.
    return {
        "side": valid_side, "entry_low": entry_low, "entry_high": entry_high,
        "stop": stop, "targets": targets, "price_near": bool(price_near),
        "fib": fib_levels(low, high, direction), "swing_low": low, "swing_high": high
    }


def build_analysis(a4, a15, a5, price):
    if not np.isfinite(a5["atr"]) or a5["atr"] <= 0:
        raise ValueError("قيمة ATR غير متاحة لحساب وقف الخسارة والأهداف")
    low, high, _, _ = swing_range(a4["df"], 80)
    # اتجاه السيناريو من توافق 4h و15m، وإلا نعرض السيناريوهين للمراقبة.
    aligned = a4["trend_value"] if a4["trend_value"] == a15["trend_value"] else 0
    directions = [aligned] if aligned in (1, -1) else [1, -1]
    scenarios = {
        d: make_scenario(d, low, high, a5["atr"], price) for d in directions
    }

    d5 = a5["df"]
    last = d5.iloc[-1]
    prior = d5.iloc[-21:-1]
    resistance, support = float(prior.high.max()), float(prior.low.min())
    rsi = a5["rsi"]
    macd_up, macd_down = a5["macd"] > a5["macd_signal"], a5["macd"] < a5["macd_signal"]
    volume_ok, volume_note = True, "الحجم غير متاح؛ لم يُستخدم كتأكيد"
    if "volume" in d5 and pd.notna(last.get("vol_avg20")) and last["vol_avg20"] > 0:
        volume_ok = bool(last.volume >= last.vol_avg20*1.10)
        volume_note = "الحجم يؤكد الحركة" if volume_ok else "الحجم لا يؤكد الحركة"

    call_ok = (a4["trend_value"] == a15["trend_value"] == a5["trend_value"] == 1
               and 50 <= rsi <= 72 and last.close > resistance and macd_up and volume_ok)
    put_ok = (a4["trend_value"] == a15["trend_value"] == a5["trend_value"] == -1
              and 28 <= rsi <= 50 and last.close < support and macd_down and volume_ok)

    confirmed = "CALL" if call_ok else "PUT" if put_ok else "WAIT"
    chosen = scenarios.get(1 if confirmed == "CALL" else -1 if confirmed == "PUT" else aligned)
    if chosen is None:
        chosen = None

    return {
        "confirmed": confirmed, "scenario": chosen, "scenarios": scenarios,
        "support": support, "resistance": resistance, "volume_note": volume_note,
        "fib4h": fib_levels(low, high, 1 if aligned != -1 else -1),
        "swing_low": low, "swing_high": high
    }


def fmt(v):
    try:
        return f"{float(v):,.2f}" if np.isfinite(float(v)) else "—"
    except Exception:
        return "—"


# ---------------- SIDEBAR ----------------
st.sidebar.markdown("## 👑 MAZONI")
st.sidebar.caption("اختر الأصل الذي تريد تحليله")
labels = list(ASSETS)
selected_label = st.sidebar.selectbox("الأصول الرئيسية", labels, index=0)
symbol = ASSETS[selected_label]
custom = st.sidebar.text_input("أو اكتب رمز سهم أمريكي", placeholder="NVDA أو TSLA").strip().upper()
if custom:
    if custom.replace(".", "").replace("-", "").isalnum():
        symbol, selected_label = custom, f"{custom} — اختيار يدوي"
    else:
        st.sidebar.error("اكتب رمزاً صحيحاً مثل NVDA")
st.sidebar.markdown("---")
st.sidebar.caption("4 ساعات للاتجاه · 15 دقيقة للتأكيد · 5 دقائق للتوقيت")
st.sidebar.caption("تحديث تلقائي كل 15 ثانية")

# ---------------- MAIN ----------------
st.markdown(f"### تحليل الأصل: `{symbol}`")
st.caption("جميع الأسعار والمستويات تخص الأصل المحدد نفسه، وليست أسعار عقود الخيارات.")

try:
    used_symbol, fallback = symbol, False
    try:
        quote = get_quote(used_symbol)
        frames = {
            "4h": analyze(get_candles(used_symbol, "4h")),
            "15m": analyze(get_candles(used_symbol, "15m")),
            "5m": analyze(get_candles(used_symbol, "5m"))
        }
    except Exception:
        if symbol != "SPX":
            raise
        used_symbol, fallback = "US500", True
        quote = get_quote(used_symbol)
        frames = {
            "4h": analyze(get_candles(used_symbol, "4h")),
            "15m": analyze(get_candles(used_symbol, "15m")),
            "5m": analyze(get_candles(used_symbol, "5m"))
        }

    price = quote.get("mid", quote.get("last", quote.get("price")))
    price = float(price)
    a4, a15, a5 = frames["4h"], frames["15m"], frames["5m"]
    result = build_analysis(a4, a15, a5, price)

    quote_age = quote.get("quoteAgeSeconds")
    fresh = not bool(quote.get("stale", False))
    if quote_age is not None:
        try:
            fresh = fresh and float(quote_age) <= 60
        except Exception:
            pass
    market_state = str(quote.get("marketState", "غير معروف")).lower()
    market_ok = market_state in ["open", "regular", "trading", "غير معروف"]
    confirmed = result["confirmed"] if fresh and market_ok else "WAIT"
    if not fresh:
        wait_reason = "السعر قديم؛ نعرض المستويات للمراقبة فقط حتى تتحدث البيانات"
    elif not market_ok:
        wait_reason = f"السوق غير مفتوح أو حالته غير مناسبة: {quote.get('marketState')}"
    else:
        wait_reason = "لم تكتمل شروط التأكيد الفني؛ راقب المنطقة ولا تعتبرها دخولاً"

    if fallback:
        st.warning("تعذر جلب SPX؛ المعروض الآن US500. جميع المستويات أدناه تخص US500 وليست SPX.")

    c1,c2,c3,c4 = st.columns(4)
    for col, label, value in [
        (c1, f"السعر الحالي · {used_symbol}", fmt(price)),
        (c2, "اتجاه 4 ساعات", a4["trend"]),
        (c3, "اتجاه 15 دقيقة", a15["trend"]),
        (c4, "اتجاه 5 دقائق", a5["trend"])
    ]:
        with col:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    if confirmed == "CALL":
        side_text, css = "دخول مؤكد فنياً · CALL", "signal-call"
        reason = "اتجاه الفريمات متوافق مع اختراق وتأكيد المؤشرات."
        active = result["scenarios"].get(1)
    elif confirmed == "PUT":
        side_text, css = "دخول مؤكد فنياً · PUT", "signal-put"
        reason = "اتجاه الفريمات متوافق مع كسر وتأكيد المؤشرات."
        active = result["scenarios"].get(-1)
    else:
        side_text, css = "انتظار · لا توجد إشارة مؤكدة", "signal-wait"
        reason = wait_reason
        active = result["scenario"]

    st.markdown(f'<div class="signal-card"><div class="{css}">{side_text}</div><div style="color:#d7d0c2;margin-top:8px">{reason}</div></div>', unsafe_allow_html=True)

    st.markdown("### منطقة الدخول والأهداف")
    if active:
        near = active["price_near"]
        status = "السعر قريب من منطقة المراقبة" if near else "السعر بعيد عن المنطقة؛ لا تطارد الحركة"
        st.info(("إشارة مؤكدة: " if confirmed != "WAIT" else "منطقة مراقبة فقط: ") + status)
        e1,e2,e3 = st.columns(3)
        e1.metric("منطقة الدخول / المراقبة", f'{fmt(active["entry_low"])} – {fmt(active["entry_high"])}')
        e2.metric("وقف الخسارة SL", fmt(active["stop"]))
        e3.metric("السعر الحالي", fmt(price))
        t1,t2,t3 = st.columns(3)
        for col, label, target in zip([t1,t2,t3],["TP1","TP2","TP3"],active["targets"]):
            col.metric(label, fmt(target))
        if confirmed == "WAIT":
            st.caption("هذه مستويات سيناريو فني وليست أمر دخول. لا تعتبرها إشارة شراء أو بيع قبل اكتمال التأكيد.")
    else:
        st.warning("اتجاه 4 ساعات و15 دقيقة غير متوافق؛ لذلك لا نرجّح جهة واحدة. راجع سيناريوهَي CALL وPUT أدناه.")

    if not active:
        for direction, title in [(1,"سيناريو CALL للمراقبة"),(-1,"سيناريو PUT للمراقبة")]:
            sc = result["scenarios"][direction]
            with st.expander(title, expanded=True):
                st.write(f'منطقة المراقبة: **{fmt(sc["entry_low"])} – {fmt(sc["entry_high"])}**')
                st.write(f'وقف السيناريو: **{fmt(sc["stop"])}**')
                st.write("الأهداف: " + " · ".join(fmt(x) for x in sc["targets"]))

    st.markdown("### مستويات فيبوناتشي · 4 ساعات")
    fib_direction = 1 if a4["trend_value"] >= 0 else -1
    fib = fib_levels(result["swing_low"], result["swing_high"], fib_direction)
    fib_df = pd.DataFrame([{"المستوى": k, "السعر": fmt(v)} for k,v in fib.items()])
    st.dataframe(fib_df, use_container_width=True, hide_index=True)
    st.caption(f'قمة النطاق: {fmt(result["swing_high"])} | قاع النطاق: {fmt(result["swing_low"])} | النطاق المستخدم: آخر 80 شمعة مغلقة من 4 ساعات.')

    st.markdown("### المؤشرات الفنية")
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("RSI · 5m", fmt(a5["rsi"]))
    m2.metric("ATR · 5m", fmt(a5["atr"]))
    m3.metric("EMA20 · 5m", fmt(a5["ema20"]))
    m4.metric("EMA50 · 5m", fmt(a5["ema50"]))
    s1,s2 = st.columns(2)
    s1.metric("الدعم التقريبي · 5m", fmt(result["support"]))
    s2.metric("المقاومة التقريبية · 5m", fmt(result["resistance"]))
    st.caption(result["volume_note"])

    with st.expander("تفاصيل الفريمات"):
        table = []
        for name, data in [("4 ساعات",a4),("15 دقيقة",a15),("5 دقائق",a5)]:
            table.append({"الفريم":name,"الاتجاه":data["trend"],"السعر":fmt(data["close"]),
                          "EMA20":fmt(data["ema20"]),"EMA50":fmt(data["ema50"]),
                          "RSI":fmt(data["rsi"]),"ATR":fmt(data["atr"])})
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    st.caption(f'مصدر البيانات: {quote.get("source","مزود البيانات")} | حالة السوق: {quote.get("marketState","غير متاحة")} | عمر السعر: {quote_age if quote_age is not None else "غير متاح"} ثانية')

except requests.exceptions.HTTPError as e:
    st.error(f"مزود البيانات لم يقبل الرمز `{symbol}` أو أن الخدمة غير متاحة.")
    st.caption(str(e))
except Exception as e:
    st.error(f"تعذر تحميل التحليل: {e}")
    st.info("تحقق من دعم مزود البيانات للرمز والفريمات المطلوبة وصيغة بيانات OHLC.")

st.markdown("---")
st.markdown('<div class="small-note">MAZONI BOT أداة تحليل فني وليست توصية مالية. الإشارة المؤكدة ليست ضماناً للربح. مستويات فيبوناتشي والسيناريوهات تقديرية ومحسوبة من آخر 80 شمعة 4 ساعات مغلقة. المستويات تخص الأصل الأساسي ولا تمثل سعر عقد الخيارات. تحقق من السعر والتنفيذ لدى وسيطك قبل التداول.</div>', unsafe_allow_html=True)
