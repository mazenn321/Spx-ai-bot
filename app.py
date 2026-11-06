
import streamlit as st
import pandas as pd
import requests
import numpy as np
import base64
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="بوت مزوني | SPX",
    page_icon="📈",
    layout="wide"
)

st_autorefresh(interval=10000, key="refresh")

API = "https://biquote.io/api"
SYMBOL = "US500"
BACKGROUND = "60494DB7-FE1A-4FC5-BB42-F385D41BA7A5.png"

# تحميل الخلفية
try:
    with open(BACKGROUND, "rb") as image_file:
        background_image = base64.b64encode(
            image_file.read()
        ).decode()
    background_css = f"""
        background-image:
        linear-gradient(rgba(5,5,5,0.72), rgba(5,5,5,0.78)),
        url("data:image/png;base64,{background_image}");
    """
except FileNotFoundError:
    background_css = "background: #080a0e;"

st.markdown(f"""
<style>
.stApp {{
    {background_css}
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
    color: #f4f4f4;
}}

header {{visibility: hidden;}}

.block-container {{
    padding-top: 1.5rem;
    max-width: 1250px;
}}

h1,h2,h3,p,label {{
    color: #f4f4f4 !important;
}}

.gold {{
    color: #d6b56d;
    font-weight: 800;
    letter-spacing: 2px;
}}

.sub {{
    color: #c0b9a9;
    font-size: 13px;
}}

.panel {{
    background: rgba(17,20,27,0.88);
    border: 1px solid #9c7d42;
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 12px;
}}

.metric-title {{
    color: #a6aab4;
    font-size: 13px;
}}

.metric-value {{
    color: #f4f4f4;
    font-size: 25px;
    font-weight: 800;
    margin-top: 7px;
}}

.gold-line {{
    border: 0;
    height: 1px;
    background: linear-gradient(90deg,transparent,#c9a65b,transparent);
    margin: 20px 0;
}}

.signal {{
    background: rgba(17,20,27,0.92);
    border: 1px solid #b9974e;
    border-radius: 18px;
    padding: 25px;
    text-align: center;
    margin: 12px 0;
}}

.signal-title {{
    color: #d6b56d;
    font-size: 13px;
    letter-spacing: 3px;
}}

.signal-value {{
    font-size: 36px;
    font-weight: 900;
    margin: 8px;
}}

div[data-testid="stDataFrame"] {{
    border: 1px solid #9c7d42;
    border-radius: 12px;
}}

.stMetric {{
    background: rgba(17,20,27,0.88);
    border: 1px solid #756039;
    padding: 12px;
    border-radius: 12px;
}}
</style>
""", unsafe_allow_html=True)


def get_json(url, params=None):
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


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
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("openTime")
    df = df.dropna(
        subset=["open", "high", "low", "close"]
    )
    df = df[df["isOpen"] == False].copy()

    if len(df) < 55:
        raise ValueError(
            f"Not enough closed candles: {interval}"
        )

    return df.reset_index(drop=True)


def indicators(df):
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

    rs = avg_gain / avg_loss.replace(0, np.nan)
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

    return df


def trend(row):
    if (
        row["ema20"] > row["ema50"]
        and row["close"] > row["ema20"]
    ):
        return "صاعد"

    if (
        row["ema20"] < row["ema50"]
        and row["close"] < row["ema20"]
    ):
        return "هابط"

    return "عرضي"


def analyze(df):
    df = indicators(df)
    last = df.iloc[-1]
    previous = df.iloc[-21:-1]

    return {
        "trend": trend(last),
        "close": float(last["close"]),
        "rsi": float(last["rsi"]),
        "atr": float(last["atr"]),
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "support": float(previous["low"].min()),
        "resistance": float(previous["high"].max()),
        "time": last["openTime"]
    }


# HEADER
st.markdown("""
<div style="text-align:center;padding:10px 0 20px">
    <div class="gold">MAZONI BOT</div>
    <h1 style="font-size:34px;margin:8px 0">
        بوت مزوني
    </h1>
    <div class="sub">
        SPX TRADING • TECHNICAL ANALYSIS
    </div>
    <div class="gold-line"></div>
</div>
""", unsafe_allow_html=True)


try:
    quote = get_quote()

    price = float(quote["mid"])
    age = int(quote.get("quoteAgeSeconds", 999999))
    stale = quote.get("stale", True)
    market = quote.get("marketState", "unknown")

    st.markdown("### 📊 بيانات السوق")

    a, b, c, d = st.columns(4)

    a.metric("US500", f"{price:.2f}")
    b.metric("Bid", f"{float(quote['bid']):.2f}")
    c.metric("Ask", f"{float(quote['ask']):.2f}")
    d.metric("عمر البيانات", f"{age} ثانية")

    st.caption(
        f"المصدر: {quote.get('source', 'غير معروف')} | "
        f"آخر تحديث: {quote.get('timestamp', '-')}"
    )

    if stale or age > 60 or market != "open":
        st.warning(
            "البيانات قديمة أو السوق مغلق. لا توجد إشارة تداول."
        )
        st.stop()

    df4 = get_candles("4h", 150)
    df15 = get_candles("15m", 200)
    df5 = get_candles("5m", 200)

    h4 = analyze(df4)
    m15 = analyze(df15)
    m5 = analyze(df5)

    st.markdown(
        '<div class="gold-line"></div>',
        unsafe_allow_html=True
    )
    st.markdown("### 🧭 اتجاه السوق")

    x, y, z = st.columns(3)

    x.metric("4 ساعات", h4["trend"])
    y.metric("15 دقيقة", m15["trend"])
    z.metric("5 دقائق", m5["trend"])

    st.markdown("### 📈 المؤشرات الفنية")

    table = pd.DataFrame([
        [
            "4 ساعات", h4["rsi"], h4["atr"],
            h4["close"], h4["ema20"], h4["ema50"]
        ],
        [
            "15 دقيقة", m15["rsi"], m15["atr"],
            m15["close"], m15["ema20"], m15["ema50"]
        ],
        [
            "5 دقائق", m5["rsi"], m5["atr"],
            m5["close"], m5["ema20"], m5["ema50"]
        ]
    ], columns=[
        "الفريم", "RSI", "ATR", "الإغلاق",
        "EMA20", "EMA50"
    ])

    st.dataframe(
        table.round(2),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### 🎯 مستويات الدعم والمقاومة")

    s, r = st.columns(2)

    s.metric("الدعم", f"{m5['support']:.2f}")
    r.metric("المقاومة", f"{m5['resistance']:.2f}")

    last5 = df5.iloc[-1]
    prev20 = df5.iloc[-21:-1]

    breakout = (
        last5["close"] > prev20["high"].max()
    )

    breakdown = (
        last5["close"] < prev20["low"].min()
    )

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

    st.markdown(
        '<div class="gold-line"></div>',
        unsafe_allow_html=True
    )
    st.markdown("### ⚡ قرار بوت مزوني")

    if call:
        entry = price
        stop = entry - (1.2 * m5["atr"])
        risk = entry - stop
        target1 = entry + (1.5 * risk)
        target2 = entry + (2.5 * risk)

        st.markdown("""
        <div class="signal">
            <div class="signal-title">
                TRADING SIGNAL
            </div>
            <div class="signal-value"
                 style="color:#24c982">
                CALL 🟢
            </div>
            <div class="sub">
                إشارة شراء مبدئية
            </div>
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
            <div class="signal-title">
                TRADING SIGNAL
            </div>
            <div class="signal-value"
                 style="color:#ff5555">
                PUT 🔴
            </div>
            <div class="sub">
                إشارة بيع مبدئية
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.markdown("""
        <div class="signal">
            <div class="signal-title">
                TRADING SIGNAL
            </div>
            <div class="signal-value"
                 style="color:#d6b56d">
                WAIT ⏳
            </div>
            <div class="sub">
                ننتظر اكتمال شروط الدخول
            </div>
        </div>
        """, unsafe_allow_html=True)

    if call or put:
        a, b = st.columns(2)
        a.metric("الدخول المرجعي", f"{entry:.2f}")
        b.metric("وقف الخسارة", f"{stop:.2f}")

        a, b = st.columns(2)
        a.metric("الهدف الأول", f"{target1:.2f}")
        b.metric("الهدف الثاني", f"{target2:.2f}")

    st.markdown(
        '<div class="gold-line"></div>',
        unsafe_allow_html=True
    )

    st.caption(
        "بوت مزوني | محرك قواعد فنية وليس نموذج ذكاء اصطناعي مدرباً. "
        "البيانات تخص US500 CFD وليست مؤشر SPX النقدي أو سعر عقد الخيارات. "
        "الإشارات والمستويات تحليلية وليست ضماناً للربح أو التنفيذ."
    )

except Exception as e:
    st.error(
        f"تعذر جلب البيانات أو تحليلها: {e}"
    )
    st.info(
        "لن يصدر البوت إشارة عند تعذر التحقق من البيانات."
    )
