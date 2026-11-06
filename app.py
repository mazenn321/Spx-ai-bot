import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# =========================================================
# MAZONI BOT | Multi-Asset Technical Levels
# يحلل الأصل نفسه فقط: دخول + أهداف + وقف خسارة
# لا يحلل عقود الخيارات ولا أسعارها أو Greeks.
# =========================================================

st.set_page_config(
    page_title="MAZONI BOT",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_BASE = "https://biquote.io/api"
REFRESH_MS = 15000
DEFAULT_SYMBOLS = {
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

# ------------------------- DESIGN -------------------------
st.markdown("""
<style>
.stApp {
    background:
      radial-gradient(circle at 15% 5%, rgba(191,151,65,.13), transparent 28%),
      linear-gradient(135deg,#07090d 0%,#10131a 55%,#07090d 100%);
    color:#f4f0e7;
}
[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#101319,#080a0e);
    border-right:1px solid rgba(201,166,92,.28);
}
h1,h2,h3 { color:#e3c477 !important; }
.mazoni-title {
    text-align:center; padding:10px 0 18px;
    color:#d7b568; font-size:38px; font-weight:900;
    letter-spacing:3px;
}
.mazoni-sub {
    text-align:center; color:#a9a39a; font-size:12px;
    letter-spacing:4px; margin-top:-14px; margin-bottom:24px;
}
.metric-card {
    background:linear-gradient(145deg,rgba(28,32,41,.96),rgba(12,15,21,.96));
    border:1px solid rgba(204,170,99,.28);
    border-radius:15px; padding:16px; min-height:100px;
}
.metric-label { color:#aaa49a; font-size:12px; margin-bottom:8px; }
.metric-value { color:#f4e6c3; font-size:23px; font-weight:800; }
.signal-card {
    background:linear-gradient(145deg,rgba(28,32,41,.98),rgba(12,15,21,.98));
    border:1px solid rgba(204,170,99,.42);
    border-radius:18px; padding:22px; margin:8px 0 16px;
}
.signal-call { color:#35d39a; font-size:34px; font-weight:900; }
.signal-put { color:#ff6b75; font-size:34px; font-weight:900; }
.signal-wait { color:#e3c477; font-size:34px; font-weight:900; }
.small-note { color:#a9a39a; font-size:12px; }
div.stButton > button {
    border:1px solid #c9a65c; color:#e7d19b;
    background:#171a20; border-radius:10px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="mazoni-title">👑 MAZONI BOT</div>', unsafe_allow_html=True)
st.markdown('<div class="mazoni-sub">SMART MARKET LEVELS</div>', unsafe_allow_html=True)

# ------------------------- DATA -------------------------
@st.cache_data(ttl=8, show_spinner=False)
def get_json(url, params=None):
    response = requests.get(
        url, params=params, timeout=12,
        headers={"User-Agent": "MAZONI-BOT/1.0"}
    )
    response.raise_for_status()
    return response.json()

def get_quote(symbol):
    data = get_json(f"{API_BASE}/{symbol}")
    if isinstance(data, dict) and "quote" in data and isinstance(data["quote"], dict):
        data = data["quote"]
    return data

def get_candles(symbol, interval, limit=250):
    data = get_json(
        f"{API_BASE}/{symbol}/ohlc",
        params={"interval": interval, "limit": limit}
    )
    if isinstance(data, dict):
        bars = data.get("bars", [])
    elif isinstance(data, list):
        bars = data
    else:
        bars = []
    if not bars:
        raise ValueError(f"لا توجد شموع للفريم {interval}")
    df = pd.DataFrame(bars)
    required = ["openTime", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"حقول الشموع ناقصة: {', '.join(missing)}")

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Biquote يوثق openTime كسلسلة ISO مثل 2026-11-06T15:30:00Z،
    # وقد يصل أحياناً كتوقيت رقمي بالثواني أو الميلي ثانية.
    # نجرب ISO أولاً حتى لا تتحول كل الصفوف إلى NaT وتصبح الشموع صفراً.
    parsed_time = pd.to_datetime(df["openTime"], utc=True, errors="coerce")
    if parsed_time.isna().all():
        raw_time = pd.to_numeric(df["openTime"], errors="coerce")
        valid_times = raw_time.dropna()
        if not valid_times.empty:
            unit = "ms" if valid_times.median() > 10**11 else "s"
            parsed_time = pd.to_datetime(raw_time, unit=unit, utc=True, errors="coerce")
    df["time"] = parsed_time
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)

    # استبعاد الشمعة المفتوحة إذا كانت حالة الحقل واضحة
    if "isOpen" in df.columns:
        open_values = df["isOpen"].astype(str).str.lower()
        df = df[~open_values.isin(["true", "1", "yes"])].copy()

    if len(df) < 60:
        raise ValueError(f"البيانات غير كافية للفريم {interval}: {len(df)} شمعة")
    return df.reset_index(drop=True)

# ------------------------- INDICATORS -------------------------
def add_indicators(df):
    x = df.copy()
    x["ema20"] = x["close"].ewm(span=20, adjust=False).mean()
    x["ema50"] = x["close"].ewm(span=50, adjust=False).mean()

    delta = x["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    x["rsi"] = 100 - (100 / (1 + rs))
    x.loc[(avg_loss == 0) & (avg_gain > 0), "rsi"] = 100
    x.loc[(avg_gain == 0) & (avg_loss > 0), "rsi"] = 0

    prev_close = x["close"].shift(1)
    tr = pd.concat([
        x["high"] - x["low"],
        (x["high"] - prev_close).abs(),
        (x["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

    ema12 = x["close"].ewm(span=12, adjust=False).mean()
    ema26 = x["close"].ewm(span=26, adjust=False).mean()
    x["macd"] = ema12 - ema26
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()

    if "volume" in x.columns and x["volume"].notna().any():
        x["vol_avg20"] = x["volume"].rolling(20).mean()
    else:
        x["vol_avg20"] = np.nan
    return x

def get_trend(row):
    if row["close"] > row["ema20"] > row["ema50"]:
        return "صاعد", 1
    if row["close"] < row["ema20"] < row["ema50"]:
        return "هابط", -1
    return "عرضي", 0

def analyze_frame(df):
    x = add_indicators(df)
    last = x.iloc[-1]
    trend_name, trend_value = get_trend(last)
    return {
        "df": x,
        "close": float(last["close"]),
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else np.nan,
        "atr": float(last["atr"]) if pd.notna(last["atr"]) else np.nan,
        "macd": float(last["macd"]),
        "macd_signal": float(last["macd_signal"]),
        "trend": trend_name,
        "trend_value": trend_value
    }

def make_signal(a4, a15, a5, live_price):
    d5 = a5["df"]
    last = d5.iloc[-1]
    prior = d5.iloc[-21:-1]
    if len(prior) < 20 or not np.isfinite(a5["atr"]) or a5["atr"] <= 0:
        return {"side": "WAIT", "reason": "البيانات غير كافية لتحديد مستويات موثوقة"}

    resistance = float(prior["high"].max())
    support = float(prior["low"].min())
    rsi = a5["rsi"]
    bullish_break = last["close"] > resistance
    bearish_break = last["close"] < support

    volume_ok = True
    volume_note = "الحجم غير متاح من مزود البيانات"
    if "volume" in d5.columns and pd.notna(last.get("vol_avg20")) and last["vol_avg20"] > 0:
        volume_ok = bool(last["volume"] >= last["vol_avg20"] * 1.15)
        volume_note = "حجم التداول أعلى من متوسطه" if volume_ok else "حجم التداول لا يؤكد الاختراق"

    up_alignment = a4["trend_value"] == 1 and a15["trend_value"] == 1 and a5["trend_value"] == 1
    down_alignment = a4["trend_value"] == -1 and a15["trend_value"] == -1 and a5["trend_value"] == -1
    macd_up = a5["macd"] > a5["macd_signal"]
    macd_down = a5["macd"] < a5["macd_signal"]

    side = "WAIT"
    reason = "لا يوجد توافق كافٍ بين الفريمات أو تأكيد للاختراق"
    if up_alignment and 50 <= rsi <= 72 and bullish_break and volume_ok and macd_up:
        side, reason = "CALL", "اتجاه صاعد متوافق مع اختراق مقاومة وتأكيد فني"
    elif down_alignment and 28 <= rsi <= 50 and bearish_break and volume_ok and macd_down:
        side, reason = "PUT", "اتجاه هابط متوافق مع كسر دعم وتأكيد فني"

    # مستويات الأصل الأساسي بالنقاط/السعر، وليست أسعار عقود الخيارات
    atr = a5["atr"]
    if side == "CALL":
        entry_low = max(live_price - 0.20 * atr, resistance)
        entry_high = entry_low + 0.25 * atr
        entry_mid = (entry_low + entry_high) / 2
        stop = entry_low - 1.20 * atr
        risk = entry_mid - stop
        targets = [entry_mid + risk, entry_mid + 1.8*risk, entry_mid + 2.6*risk]
    elif side == "PUT":
        entry_high = min(live_price + 0.20 * atr, support)
        entry_low = entry_high - 0.25 * atr
        entry_mid = (entry_low + entry_high) / 2
        stop = entry_high + 1.20 * atr
        risk = stop - entry_mid
        targets = [entry_mid - risk, entry_mid - 1.8*risk, entry_mid - 2.6*risk]
    else:
        entry_low = entry_high = stop = np.nan
        targets = [np.nan, np.nan, np.nan]

    # تقييم قوة الإعداد الفني وليس احتمالية ربح مضمونة
    score = 0
    score += 25 if up_alignment or down_alignment else 0
    score += 20 if (bullish_break or bearish_break) else 0
    score += 15 if (macd_up and side == "CALL") or (macd_down and side == "PUT") else 0
    score += 15 if volume_ok else 0
    score += 15 if (side == "CALL" and 52 <= rsi <= 68) or (side == "PUT" and 32 <= rsi <= 48) else 0
    score += 10 if side != "WAIT" else 0
    if side == "WAIT":
        score = min(score, 49)

    return {
        "side": side, "reason": reason, "score": score,
        "entry_low": entry_low, "entry_high": entry_high,
        "stop": stop, "targets": targets,
        "support": support, "resistance": resistance,
        "volume_note": volume_note
    }

def fmt(value):
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:,.2f}"

# ------------------------- SIDEBAR -------------------------
st.sidebar.markdown("## 👑 MAZONI")
st.sidebar.caption("اختر الأصل الذي تريد تحليله")

labels = list(DEFAULT_SYMBOLS.keys())
selected_label = st.sidebar.selectbox("الأصول الرئيسية", labels, index=0)
selected_symbol = DEFAULT_SYMBOLS[selected_label]

st.sidebar.markdown("---")
custom_symbol = st.sidebar.text_input(
    "أو اكتب رمز سهم أمريكي",
    placeholder="مثال: NVDA أو TSLA"
).strip().upper()

if custom_symbol:
    if custom_symbol.replace(".", "").replace("-", "").isalnum():
        selected_symbol = custom_symbol
        selected_label = f"{custom_symbol} — اختيار يدوي"
    else:
        st.sidebar.error("اكتب رمزاً صحيحاً مثل NVDA")

st.sidebar.markdown("---")
st.sidebar.caption("الفريمات: 4 ساعات / 15 دقيقة / 5 دقائق")
st.sidebar.caption("تحديث تلقائي كل 15 ثانية")
st.sidebar.caption("البيانات تعتمد على دعم مزود الخدمة للرمز المطلوب.")

# ------------------------- MAIN -------------------------
st.markdown(f"### تحليل الأصل: `{selected_symbol}`")
st.caption("المستويات المعروضة تخص الأصل المختار نفسه، ولا تمثل سعر عقد خيارات.")

try:
    used_symbol = selected_symbol
    fallback_used = False

    # SPX هو الأساس. لا نخلط سعر US500 بمستويات SPX؛ عند الفشل نعرضه كأصل بديل بوضوح.
    try:
        quote = get_quote(used_symbol)
        frames = {
            "4h": analyze_frame(get_candles(used_symbol, "4h")),
            "15m": analyze_frame(get_candles(used_symbol, "15m")),
            "5m": analyze_frame(get_candles(used_symbol, "5m")),
        }
    except Exception as primary_error:
        if selected_symbol == "SPX":
            used_symbol = "US500"
            fallback_used = True
            quote = get_quote(used_symbol)
            frames = {
                "4h": analyze_frame(get_candles(used_symbol, "4h")),
                "15m": analyze_frame(get_candles(used_symbol, "15m")),
                "5m": analyze_frame(get_candles(used_symbol, "5m")),
            }
        else:
            raise primary_error

    price = quote.get("mid")
    if price is None:
        price = quote.get("last", quote.get("price"))
    price = float(price)

    quote_age = quote.get("quoteAgeSeconds")
    stale = bool(quote.get("stale", False))
    market_state = str(quote.get("marketState", "غير معروف")).lower()
    data_source = quote.get("source", "مزود البيانات")
    a4, a15, a5 = frames["4h"], frames["15m"], frames["5m"]

    signal = make_signal(a4, a15, a5, price)

    # تعطيل الإشارة عند قدم السعر أو إشارة stale؛ لا نخفي التحليل لكن نمنع توصية جديدة.
    fresh = not stale
    if quote_age is not None:
        try:
            fresh = fresh and float(quote_age) <= 60
        except Exception:
            pass
    if not fresh:
        signal["side"] = "WAIT"
        signal["reason"] = "السعر قديم أو البيانات معلّمة بأنها غير محدثة؛ انتظر تحديث البيانات"
    if market_state not in ["open", "regular", "trading", "غير معروف"]:
        signal["side"] = "WAIT"
        signal["reason"] = f"حالة السوق: {quote.get('marketState')} — لا توجد إشارة دخول جديدة"

    if fallback_used:
        st.warning(
            "تعذر جلب SPX من مزود البيانات؛ تم عرض US500 كبديل. "
            "المستويات التالية تخص US500 وليست مستويات SPX."
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">السعر الحالي · {used_symbol}</div><div class="metric-value">{fmt(price)}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">اتجاه 4 ساعات</div><div class="metric-value">{a4["trend"]}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">اتجاه 15 دقيقة</div><div class="metric-value">{a15["trend"]}</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><div class="metric-label">اتجاه 5 دقائق</div><div class="metric-value">{a5["trend"]}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    side = signal["side"]
    side_class = "signal-call" if side == "CALL" else "signal-put" if side == "PUT" else "signal-wait"
    side_ar = "شراء CALL — اتجاه صاعد" if side == "CALL" else "شراء PUT — اتجاه هابط" if side == "PUT" else "انتظار"
    st.markdown(
        f'<div class="signal-card"><div class="{side_class}">{side_ar}</div>'
        f'<div style="color:#d7d0c2;margin-top:8px">{signal["reason"]}</div>'
        f'<div style="color:#b9a77e;margin-top:12px">قوة الإعداد الفني: {signal["score"]}/100</div></div>',
        unsafe_allow_html=True
    )

    if side != "WAIT":
        p1, p2, p3 = st.columns(3)
        with p1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">منطقة الدخول</div><div class="metric-value">{fmt(signal["entry_low"])} – {fmt(signal["entry_high"])}</div></div>', unsafe_allow_html=True)
        with p2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">وقف الخسارة SL</div><div class="metric-value">{fmt(signal["stop"])}</div></div>', unsafe_allow_html=True)
        with p3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">الهدف الأول TP1</div><div class="metric-value">{fmt(signal["targets"][0])}</div></div>', unsafe_allow_html=True)

        t1, t2, t3 = st.columns(3)
        for col, title, target in [
            (t1, "الهدف الأول TP1", signal["targets"][0]),
            (t2, "الهدف الثاني TP2", signal["targets"][1]),
            (t3, "الهدف الثالث TP3", signal["targets"][2]),
        ]:
            with col:
                st.metric(title, fmt(target))
    else:
        st.info("لا توجد صفقة مكتملة الشروط الآن. لا تدخل لمجرد أن السعر يتحرك.")

    st.markdown("### المؤشرات الفنية")
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("RSI · 5m", fmt(a5["rsi"]))
    i2.metric("ATR · 5m", fmt(a5["atr"]))
    i3.metric("EMA 20 · 5m", fmt(a5["ema20"]))
    i4.metric("EMA 50 · 5m", fmt(a5["ema50"]))

    s1, s2 = st.columns(2)
    s1.metric("الدعم التقريبي · 5m", fmt(signal["support"]))
    s2.metric("المقاومة التقريبية · 5m", fmt(signal["resistance"]))
    st.caption(signal["volume_note"])

    with st.expander("تفاصيل الفريمات"):
        rows = []
        for name, data in [("4 ساعات", a4), ("15 دقيقة", a15), ("5 دقائق", a5)]:
            rows.append({
                "الفريم": name,
                "الاتجاه": data["trend"],
                "الإغلاق": fmt(data["close"]),
                "EMA20": fmt(data["ema20"]),
                "EMA50": fmt(data["ema50"]),
                "RSI": fmt(data["rsi"]),
                "ATR": fmt(data["atr"]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.caption(
        f"مصدر البيانات: {data_source} | حالة السوق: {quote.get('marketState', 'غير متاحة')} "
        f"| عمر السعر: {quote_age if quote_age is not None else 'غير متاح'} ثانية"
    )

except requests.exceptions.HTTPError as e:
    st.error(
        f"مزود البيانات لم يقبل الرمز `{selected_symbol}` أو أن الخدمة غير متاحة. "
        "قد لا يدعم المزود جميع الأسهم أو رمز SPX. جرّب رمزاً آخر أو تحقق من اشتراك/توثيق مزود البيانات."
    )
    st.caption(str(e))
except Exception as e:
    st.error(f"تعذر تحميل التحليل: {e}")
    st.info(
        "تأكد من أن مزود البيانات يدعم الرمز والفريمات المطلوبة، "
        "وأن صيغة استجابة الشموع تحتوي openTime وopen وhigh وlow وclose."
    )

st.markdown("---")
st.markdown(
    '<div class="small-note">MAZONI BOT أداة تحليل فني وليست توصية مالية. '
    'المستويات تخص المؤشر أو السهم الأساسي، ولا تمثل أسعار عقود الخيارات. '
    'درجة القوة تقييم لقواعد فنية وليست نسبة نجاح مثبتة. تحقق من السعر والتنفيذ لدى وسيطك قبل التداول.</div>',
    unsafe_allow_html=True
)
