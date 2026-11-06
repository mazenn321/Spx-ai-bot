
import streamlit as st
import pandas as pd
import requests
from streamlit_autorefresh import st_autorefresh

# ==========================================
# MAZONI BOT
# ==========================================

st.set_page_config(
    page_title="بوت مزوني | SPX",
    page_icon="👑",
    layout="wide"
)

st_autorefresh(interval=10000, key="mazoni_refresh")

API = "https://biquote.io/api"
SYMBOL = "US500"

# ==========================================
# SIMPLE BLACK DESIGN
# ==========================================

st.markdown("""
<style>
.stApp {
    background: #080a0e;
    color: #f5f0e5;
}
header, footer {
    visibility: hidden;
}
.block-container {
    max-width: 1200px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}
h1, h2, h3, p, label {
    color: #f5f0e5 !important;
}
.gold-line {
    height: 1px;
    background: #80683c;
    margin: 20px 0;
}
.stMetric {
    background: #11151d;
    border: 1px solid #80683c;
    padding: 12px;
    border-radius: 12px;
}
.signal {
    background: #11151d;
    border: 1px solid #80683c;
    border-radius: 16px;
    text-align: center;
    padding: 24px 12px;
    margin: 12px 0;
}
.signal-value {
    font-size: 38px;
    font-weight: 900;
    margin: 8px;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# DATA
# ==========================================

def get_json(url, params=None):
    response = requests.get(
        url,
        params=params,
        timeout=15
    )
    response.raise_for_status()
    return response.json()


def get_quote():
    return get_json(f"{API}/{SYMBOL}")


def get_candles(interval, limit=200):
    data = get_json(
        f"{API}/{SYMBOL}/ohlc",
        {"interval": interval, "limit": limit}
    )

    df = pd.DataFrame(data["bars"])

    if df.empty:
        raise ValueError(f"No candles: {interval}")

    df["openTime"] = pd.to_datetime(
        df["openTime"], utc=True
    )

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(
            df[col], errors="coerce"
        )

    df = df.sort_values("openTime").dropna(
        subset=["open", "high", "low", "close"]
    )

    if "isOpen" in df.columns:
        closed = (
            df["isOpen"].astype(str).str.lower()
            .isin(["false", "0"])
        )
        df = df[closed].copy()

    if len(df) < 55:
        raise ValueError(
            f"Not enough closed candles: {interval}"
        )

    return df.reset_index(drop=True)


# ==========================================
# INDICATORS
# ==========================================

def analyze(df):
    df = df.copy()

    df["ema20"] = df["close"].ewm(
        span=20, adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50, adjust=False
    ).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14, adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    df["rsi"] = 100 - (100 / (1 + rs))

    previous = df["close"].shift(1)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous).abs(),
        (df["low"] - previous).abs()
    ], axis=1).max(axis=1)

    df["atr"] = tr.ewm(
        alpha=1/14, adjust=False
    ).mean()

    last = df.iloc[-1]
    previous20 = df.iloc[-21:-1]

    if last["ema20"] > last["ema50"] and last["close"] > last["ema20"]:
        trend = "صاعد"
    elif last["ema20"] < last["ema50"] and last["close"] < last["ema20"]:
        trend = "هابط"
    else:
        trend = "عرضي"

    return {
        "trend": trend,
        "close": float(last["close"]),
        "rsi": float(last["rsi"]),
        "atr": float(last["atr"]),
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "support": float(previous20["low"].min()),
        "resistance": float(previous20["high"].max()),
        "time": last["openTime"]
    }


# ==========================================
# MAIN ENGINE
# ==========================================

try:
    quote = get_quote()

    price = float(quote["mid"])
    bid = float(quote["bid"])
    ask = float(quote["ask"])

    age = int(quote.get("quoteAgeSeconds", 999999))
    stale = quote.get("stale", True)
    market = quote.get("marketState", "unknown")

    st.markdown("## 📊 بيانات السوق")

    a, b, c, d = st.columns(4)
    a.metric("US500", f"{price:,.2f}")
    b.metric("BID", f"{bid:,.2f}")
    c.metric("ASK", f"{ask:,.2f}")
    d.metric("عمر البيانات", f"{age} ثانية")

    st.caption(
        f"المصدر: {quote.get('source', 'غير معروف')} | "
        f"حالة السوق: {market} | "
        f"آخر تحديث: {quote.get('timestamp', '-')}"
    )

    if stale or age > 60 or market != "open":
        st.warning(
            "البيانات قديمة أو السوق مغلق. لن يصدر البوت إشارة تداول."
        )
        st.stop()

    # FETCH TIMEFRAMES

    h4 = analyze(get_candles("4h", 150))
    m15 = analyze(get_candles("15m", 200))
    m5 = analyze(get_candles("5m", 200))

    # TREND

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)
    st.markdown("## 🧭 اتجاه السوق")

    x, y, z = st.columns(3)
    x.metric("4 ساعات", h4["trend"])
    y.metric("15 دقيقة", m15["trend"])
    z.metric("5 دقائق", m5["trend"])

    # INDICATORS

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)
    st.markdown("## 📋 المؤشرات الفنية")

    table = pd.DataFrame([
        ["4 ساعات", h4["rsi"], h4["atr"], h4["ema20"], h4["ema50"]],
        ["15 دقيقة", m15["rsi"], m15["atr"], m15["ema20"], m15["ema50"]],
        ["5 دقائق", m5["rsi"], m5["atr"], m5["ema20"], m5["ema50"]]
    ], columns=[
        "الفريم", "RSI", "ATR", "EMA20", "EMA50"
    ])

    st.dataframe(
        table.round(2),
        use_container_width=True,
        hide_index=True
    )

    # SUPPORT AND RESISTANCE

    st.markdown("## 🎯 الدعم والمقاومة")

    s, r = st.columns(2)
    s.metric("الدعم", f"{m5['support']:.2f}")
    r.metric("المقاومة", f"{m5['resistance']:.2f}")

    # SIGNAL RULES

    last5 = get_candles("5m", 200)
    last_candle = last5.iloc[-1]
    previous20 = last5.iloc[-21:-1]

    breakout = last_candle["close"] > previous20["high"].max()
    breakdown = last_candle["close"] < previous20["low"].min()

    call = (
        h4["trend"] == "صاعد"
        and m15["trend"] == "صاعد"
        and m5["trend"] == "صاعد"
        and 50 <= m5["rsi"] <= 70
        and breakout
    )

    put = (
        h4["trend"] == "هابط"
        and m15["trend"] == "هابط"
        and m5["trend"] == "هابط"
        and 30 <= m5["rsi"] <= 50
        and breakdown
    )

    # SIGNAL DISPLAY

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)
    st.markdown("## ⚡ قرار بوت مزوني")

    if call:
        entry = price
        stop = entry - (1.2 * m5["atr"])
        risk = entry - stop
        target1 = entry + (1.5 * risk)
        target2 = entry + (2.5 * risk)

        st.markdown("""
        <div class="signal">
            <div class="signal-value" style="color:#19c783">
                CALL 🟢
            </div>
            <p>إشارة شراء مبدئية</p>
        </div>
        """, unsafe_allow_html=True)

    elif put:
        entry = price
        stop = entry + (1.2 * m5["atr"])
        risk = stop - entry
        target1 = entry - (1.5 * risk)
        target2 = entry - (2.5 * risk)

        st.markdown("""
        <div class="signal">
            <div class="signal-value" style="color:#ff4d5a">
                PUT 🔴
            </div>
            <p>إشارة بيع مبدئية</p>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.markdown("""
        <div class="signal">
            <div class="signal-value" style="color:#d7b56d">
                WAIT ⏳
            </div>
            <p>ننتظر اكتمال شروط الدخول</p>
        </div>
        """, unsafe_allow_html=True)

    # TRADE LEVELS

    if call or put:
        st.markdown("### مستويات الصفقة")

        a, b = st.columns(2)
        a.metric("الدخول المرجعي", f"{entry:.2f}")
        b.metric("وقف الخسارة", f"{stop:.2f}")

        a, b = st.columns(2)
        a.metric("الهدف الأول", f"{target1:.2f}")
        b.metric("الهدف الثاني", f"{target2:.2f}")

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)

    st.caption(
        "MAZONI BOT | محرك قواعد فنية وليس ذكاءً اصطناعياً مدرباً. "
        "البيانات تخص US500 CFD وليست مؤشر SPX النقدي أو سعر عقد الخيارات. "
        "تحديث الواجهة كل 10 ثوانٍ لا يضمن تحديث المصدر بنفس التواتر. "
        "الإشارات تحليلية وليست ضماناً للربح. عقود 0DTE عالية المخاطر."
    )

except Exception as e:
    st.error(f"تعذر جلب البيانات أو تحليلها: {e}")
    st.info("لن يصدر البوت إشارة عند تعذر التحقق من البيانات.")
