
import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="SPX AI Signals",
    page_icon="📈",
    layout="wide"
)

st_autorefresh(interval=10000, key="refresh")

API = "https://biquote.io/api"
SYMBOL = "US500"

st.title("📈 SPX Trading Signals")
st.caption("US500 CFD | 4H + 15M + 5M")

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
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[df["isOpen"] == False].copy()

    if len(df) < 55:
        raise ValueError(f"Not enough closed candles: {interval}")

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
    if row["ema20"] > row["ema50"] and row["close"] > row["ema20"]:
        return "صاعد"
    if row["ema20"] < row["ema50"] and row["close"] < row["ema20"]:
        return "هابط"
    return "عرضي"

def analyze(df):
    df = indicators(df)
    last = df.iloc[-1]
    previous = df.iloc[-21:-1]

    resistance = previous["high"].max()
    support = previous["low"].min()

    return {
        "trend": trend(last),
        "close": float(last["close"]),
        "rsi": float(last["rsi"]),
        "atr": float(last["atr"]),
        "ema20": float(last["ema20"]),
        "ema50": float(last["ema50"]),
        "support": float(support),
        "resistance": float(resistance),
        "time": last["openTime"]
    }

try:
    quote = get_quote()

    price = float(quote["mid"])
    age = int(quote.get("quoteAgeSeconds", 999999))
    stale = quote.get("stale", True)
    market = quote.get("marketState", "unknown")

    st.subheader("السعر المباشر من المصدر")
    a, b, c, d = st.columns(4)

    a.metric("US500", f"{price:.2f}")
    b.metric("Bid", f"{quote['bid']:.2f}")
    c.metric("Ask", f"{quote['ask']:.2f}")
    d.metric("عمر البيانات", f"{age} ثانية")

    st.caption(
        f"المصدر: {quote.get('source', 'غير معروف')} | "
        f"آخر تحديث: {quote.get('timestamp', '-')}"
    )

    if stale or age > 60 or market != "open":
        st.error("البيانات قديمة أو السوق مغلق. لا توجد إشارة تداول.")
        st.stop()

    df4 = get_candles("4h", 150)
    df15 = get_candles("15m", 200)
    df5 = get_candles("5m", 200)

    h4 = analyze(df4)
    m15 = analyze(df15)
    m5 = analyze(df5)

    st.divider()
    st.subheader("تحليل الاتجاه")

    x, y, z = st.columns(3)

    x.metric("4 ساعات", h4["trend"])
    y.metric("15 دقيقة", m15["trend"])
    z.metric("5 دقائق", m5["trend"])

    st.subheader("المؤشرات الفنية")

    table = pd.DataFrame([
        ["4 ساعات", h4["rsi"], h4["atr"], h4["close"]],
        ["15 دقيقة", m15["rsi"], m15["atr"], m15["close"]],
        ["5 دقائق", m5["rsi"], m5["atr"], m5["close"]]
    ], columns=["الفريم", "RSI", "ATR", "الإغلاق"])

    st.dataframe(table, use_container_width=True)

    st.subheader("الدعم والمقاومة - فريم 5 دقائق")

    s, r = st.columns(2)
    s.metric("الدعم", f"{m5['support']:.2f}")
    r.metric("المقاومة", f"{m5['resistance']:.2f}")

    # شروط الاختراق والكسر على آخر شمعة مغلقة
    last5 = df5.iloc[-1]
    prev20 = df5.iloc[-21:-1]

    breakout = last5["close"] > prev20["high"].max()
    breakdown = last5["close"] < prev20["low"].min()

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

    st.divider()
    st.subheader("قرار التداول")

    if call:
        entry = price
        stop = entry - (1.2 * m5["atr"])
        risk = entry - stop
        target1 = entry + (1.5 * risk)
        target2 = entry + (2.5 * risk)

        st.success("🟢 CALL - إشارة شراء مبدئية")
        st.metric("الدخول المرجعي", f"{entry:.2f}")
        st.metric("وقف الخسارة", f"{stop:.2f}")
        st.metric("الهدف الأول", f"{target1:.2f}")
        st.metric("الهدف الثاني", f"{target2:.2f}")

    elif put:
        entry = price
        stop = entry + (1.2 * m5["atr"])
        risk = stop - entry
        target1 = entry - (1.5 * risk)
        target2 = entry - (2.5 * risk)

        st.error("🔴 PUT - إشارة بيع مبدئية")
        st.metric("الدخول المرجعي", f"{entry:.2f}")
        st.metric("وقف الخسارة", f"{stop:.2f}")
        st.metric("الهدف الأول", f"{target1:.2f}")
        st.metric("الهدف الثاني", f"{target2:.2f}")

    else:
        st.warning("⏳ انتظار - شروط الدخول غير مكتملة")
        st.write("ننتظر توافق الاتجاه والاختراق أو الكسر.")

    st.caption(
        "تنبيه: هذا محرك قواعد فنية وليس نموذج ذكاء اصطناعي مدرباً. "
        "الأسعار تخص US500 CFD وليست SPX النقدي أو سعر عقد الخيارات. "
        "مستويات الوقف والأهداف تحليلية وليست ضماناً للتنفيذ."
    )

except Exception as e:
    st.error(f"تعذر جلب البيانات أو تحليلها: {e}")
    st.info("لن يصدر البوت إشارة عند تعذر التحقق من البيانات.")
