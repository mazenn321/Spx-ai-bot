
import streamlit as st
import pandas as pd
import requests
import numpy as np
import base64
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ==========================================
# MAZONI BOT | SPX TECHNICAL ANALYSIS
# ==========================================

st.set_page_config(
    page_title="MAZONI BOT | SPX",
    page_icon="👑",
    layout="wide"
)

st_autorefresh(interval=10000, key="mazoni_refresh")

API = "https://biquote.io/api"
SYMBOL = "US500"
BACKGROUND = "60494DB7-FE1A-4FC5-BB42-F385D41BA7A5.png"

# ==========================================
# DESIGN
# ==========================================

try:
    with open(BACKGROUND, "rb") as f:
        bg = base64.b64encode(f.read()).decode()
    background_css = f"""
    background-image:
    linear-gradient(rgba(3,5,9,.90),rgba(3,5,9,.94)),
    url("data:image/png;base64,{bg}");
    """
except Exception:
    background_css = "background:#080a0e;"

st.markdown(f"""
<style>
.stApp {{
    {background_css}
    background-size:cover;
    background-position:center;
    background-attachment:fixed;
    color:#f5f0e5;
}}

header {{visibility:hidden;}}

.block-container {{
    max-width:1350px;
    padding-top:1.2rem;
    padding-bottom:3rem;
}}

h1,h2,h3,p,label {{
    color:#f5f0e5 !important;
}}

.gold {{
    color:#d7b56d;
    letter-spacing:4px;
    font-weight:900;
}}

.subtitle {{
    color:#a9a08d;
    font-size:12px;
    letter-spacing:2px;
}}

.panel {{
    background:rgba(12,16,23,.94);
    border:1px solid rgba(201,165,91,.55);
    border-radius:16px;
    padding:18px;
    margin-bottom:14px;
}}

.metric-box {{
    background:rgba(12,16,23,.94);
    border:1px solid #80683c;
    border-radius:14px;
    padding:15px;
    min-height:95px;
}}

.metric-label {{
    color:#a9a08d;
    font-size:12px;
}}

.metric-number {{
    color:#f5f0e5;
    font-size:25px;
    font-weight:800;
    margin-top:8px;
}}

.gold-line {{
    height:1px;
    background:linear-gradient(
        90deg,transparent,#d7b56d,transparent
    );
    margin:22px 0;
}}

.signal {{
    background:rgba(10,14,20,.96);
    border:1px solid #b99550;
    border-radius:20px;
    text-align:center;
    padding:25px 12px;
    margin:12px 0;
}}

.signal-title {{
    color:#d7b56d;
    letter-spacing:4px;
    font-size:12px;
}}

.signal-value {{
    font-size:40px;
    font-weight:900;
    margin:8px;
}}

.stMetric {{
    background:rgba(12,16,23,.94);
    border:1px solid #80683c;
    padding:12px;
    border-radius:12px;
}}

div[data-testid="stDataFrame"] {{
    border:1px solid #80683c;
    border-radius:12px;
}}

.stSelectbox div[data-baseweb="select"] {{
    background:#10151d;
}}

footer {{visibility:hidden;}}
</style>
""", unsafe_allow_html=True)


# ==========================================
# DATA FUNCTIONS
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
        {
            "interval": interval,
            "limit": limit
        }
    )

    df = pd.DataFrame(data["bars"])

    if df.empty:
        raise ValueError(f"No candles: {interval}")

    df["openTime"] = pd.to_datetime(
        df["openTime"],
        utc=True
    )

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.sort_values("openTime")

    df = df.dropna(
        subset=["open", "high", "low", "close"]
    )

    if "isOpen" in df.columns:
        df = df[
            df["isOpen"].astype(str).str.lower()
            .isin(["false", "0"])
        ].copy()

    if len(df) < 55:
        raise ValueError(
            f"Not enough closed candles: {interval}"
        )

    return df.reset_index(drop=True)


# ==========================================
# INDICATORS
# ==========================================

def indicators(df):
    df = df.copy()

    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["rsi"] = 100 - (100 / (1 + rs))

    previous = df["close"].shift(1)

    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous).abs(),
            (df["low"] - previous).abs()
        ],
        axis=1
    ).max(axis=1)

    df["atr"] = tr.ewm(
        alpha=1/14,
        adjust=False
    ).mean()

    return df


def get_trend(row):
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
        "df": df,
        "trend": get_trend(last),
        "close": float(last["close"]),
        "rsi": float(last["rsi"]),
        "atr": float(last["atr"]),
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "support": float(previous["low"].min()),
        "resistance": float(previous["high"].max()),
        "time": last["openTime"]
    }


# ==========================================
# CHART
# ==========================================

def make_chart(df, title):
    chart = go.Figure()

    chart.add_trace(
        go.Candlestick(
            x=df["openTime"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Candles",
            increasing_line_color="#19c783",
            decreasing_line_color="#ff4d5a"
        )
    )

    chart.add_trace(
        go.Scatter(
            x=df["openTime"],
            y=df["ema20"],
            name="EMA 20",
            line=dict(
                color="#d7b56d",
                width=2
            )
        )
    )

    chart.add_trace(
        go.Scatter(
            x=df["openTime"],
            y=df["ema50"],
            name="EMA 50",
            line=dict(
                color="#48a9ff",
                width=2
            )
        )
    )

    previous = df.iloc[-21:-1]

    support = float(previous["low"].min())
    resistance = float(previous["high"].max())

    chart.add_hline(
        y=support,
        line_dash="dot",
        line_color="#19c783",
        annotation_text="SUPPORT"
    )

    chart.add_hline(
        y=resistance,
        line_dash="dot",
        line_color="#ff5964",
        annotation_text="RESISTANCE"
    )

    chart.update_layout(
        title=dict(
            text=title,
            font=dict(color="#d7b56d", size=16)
        ),
        template="plotly_dark",
        paper_bgcolor="rgba(8,10,15,0)",
        plot_bgcolor="rgba(8,10,15,.7)",
        font=dict(color="#eee5d2"),
        height=480,
        margin=dict(l=10, r=10, t=55, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h",
            y=1.08,
            x=0
        ),
        uirevision=title
    )

    chart.update_xaxes(
        showgrid=True,
        gridcolor="rgba(150,150,150,.12)"
    )

    chart.update_yaxes(
        showgrid=True,
        gridcolor="rgba(150,150,150,.12)"
    )

    return chart


# ==========================================
# HEADER
# ==========================================

st.markdown("""
<div style="text-align:center;padding:12px 0 22px">

    <div style="font-size:40px">👑</div>

    <div class="gold" style="font-size:25px">
        MAZONI BOT
    </div>

    <h1 style="font-size:34px;margin:8px 0">
        بوت مزوني
    </h1>

    <div class="subtitle">
        SMART MARKET ANALYSIS
    </div>

    <div style="
        color:#c6a45e;
        font-size:25px;
        margin-top:10px;">
        🐂　⚔　🐻
    </div>

    <div class="gold-line"></div>

</div>
""", unsafe_allow_html=True)


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

    # MARKET DATA

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
            "البيانات قديمة أو السوق مغلق. "
            "لن يصدر البوت إشارة تداول."
        )

        st.stop()

    # FETCH TIMEFRAMES

    df4 = get_candles("4h", 150)
    df15 = get_candles("15m", 200)
    df5 = get_candles("5m", 200)

    h4 = analyze(df4)
    m15 = analyze(df15)
    m5 = analyze(df5)

    # TREND

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)

    st.markdown("## 🧭 اتجاه السوق")

    x, y, z = st.columns(3)

    x.metric("4 ساعات", h4["trend"])
    y.metric("15 دقيقة", m15["trend"])
    z.metric("5 دقائق", m5["trend"])

    # CHART SELECTOR

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)

    st.markdown("## 📈 الشارت الفني")

    timeframe = st.selectbox(
        "اختر الفريم",
        [
            "4 ساعات",
            "15 دقيقة",
            "5 دقائق"
        ]
    )

    if timeframe == "4 ساعات":
        selected_df = h4["df"]
        selected_title = "US500 | 4H"
    elif timeframe == "15 دقيقة":
        selected_df = m15["df"]
        selected_title = "US500 | 15M"
    else:
        selected_df = m5["df"]
        selected_title = "US500 | 5M"

    fig = make_chart(
        selected_df,
        selected_title
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
            "scrollZoom": True
        }
    )

    # INDICATORS TABLE

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)

    st.markdown("## 📋 المؤشرات الفنية")

    table = pd.DataFrame([
        [
            "4 ساعات",
            h4["rsi"],
            h4["atr"],
            h4["ema20"],
            h4["ema50"]
        ],
        [
            "15 دقيقة",
            m15["rsi"],
            m15["atr"],
            m15["ema20"],
            m15["ema50"]
        ],
        [
            "5 دقائق",
            m5["rsi"],
            m5["atr"],
            m5["ema20"],
            m5["ema50"]
        ]
    ], columns=[
        "الفريم",
        "RSI",
        "ATR",
        "EMA20",
        "EMA50"
    ])

    st.dataframe(
        table.round(2),
        use_container_width=True,
        hide_index=True
    )

    # SUPPORT AND RESISTANCE

    st.markdown("## 🎯 الدعم والمقاومة")

    s, r = st.columns(2)

    s.metric(
        "الدعم",
        f"{m5['support']:.2f}"
    )

    r.metric(
        "المقاومة",
        f"{m5['resistance']:.2f}"
    )

    # SIGNAL CONDITIONS - ORIGINAL RULES

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
            <div class="signal-title">
                MAZONI TRADING SIGNAL
            </div>
            <div class="signal-value"
                 style="color:#19c783">
                CALL 🟢
            </div>
            <div class="subtitle">
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
                MAZONI TRADING SIGNAL
            </div>
            <div class="signal-value"
                 style="color:#ff4d5a">
                PUT 🔴
            </div>
            <div class="subtitle">
                إشارة بيع مبدئية
            </div>
        </div>
        """, unsafe_allow_html=True)

    else:

        st.markdown("""
        <div class="signal">
            <div class="signal-title">
                MAZONI TRADING SIGNAL
            </div>
            <div class="signal-value"
                 style="color:#d7b56d">
                WAIT ⏳
            </div>
            <div class="subtitle">
                ننتظر اكتمال شروط الدخول
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ENTRY / STOP / TARGETS

    if call or put:

        st.markdown("### مستويات الصفقة")

        a, b = st.columns(2)

        a.metric(
            "الدخول المرجعي",
            f"{entry:.2f}"
        )

        b.metric(
            "وقف الخسارة",
            f"{stop:.2f}"
        )

        a, b = st.columns(2)

        a.metric(
            "الهدف الأول",
            f"{target1:.2f}"
        )

        b.metric(
            "الهدف الثاني",
            f"{target2:.2f}"
        )

    # FOOTER

    st.markdown('<div class="gold-line"></div>',
                unsafe_allow_html=True)

    st.caption(
        "MAZONI BOT | محرك قواعد فنية وليس نموذج ذكاء اصطناعي مدرباً. "
        "البيانات تخص US500 CFD وليست مؤشر SPX النقدي أو سعر عقد الخيارات. "
        "التحديث التلقائي للواجهة كل 10 ثوانٍ لا يضمن تحديث المصدر بنفس التواتر. "
        "الإشارات والمستويات تحليلية وليست ضماناً للربح أو التنفيذ. "
        "عقود 0DTE عالية المخاطر."
    )

except Exception as e:

    st.error(
        f"تعذر جلب البيانات أو تحليلها: {e}"
    )

    st.info(
        "لن يصدر البوت إشارة عند تعذر التحقق من البيانات."
    )
