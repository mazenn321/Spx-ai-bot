import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(page_title="SPX AI Signals", page_icon="📈", layout="centered")

st.title("📈 SPX AI Trading Signals")
st.caption("SPX | تحليل فني لعقود 0DTE")

st.warning(
    "تنبيه: البيانات من Yahoo Finance وليست مضمونة اللحظية. "
    "لا تنفذ صفقة قبل التأكد من السعر المباشر في دراية."
)

@st.cache_data(ttl=60)
def get_data(symbol):
    return yf.Ticker(symbol).history(period="1d", interval="5m")

def rsi_calc(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, 0.000001)
    return 100 - (100 / (1 + rs))

if st.button("🔄 تحديث التحليل", use_container_width=True):
    st.cache_data.clear()

try:
    spx = get_data("^GSPC")
    spy = get_data("SPY")
    vix = get_data("^VIX")

    if spx.empty or spy.empty or vix.empty:
        st.error("تعذر جلب البيانات. حاول لاحقًا.")
        st.stop()

    spx = spx.dropna()
    spy = spy.dropna()
    vix = vix.dropna()

    spx["EMA9"] = spx["Close"].ewm(span=9).mean()
    spx["EMA20"] = spx["Close"].ewm(span=20).mean()
    spx["RSI"] = rsi_calc(spx["Close"])

    spy["VWAP"] = (
        ((spy["High"] + spy["Low"] + spy["Close"]) / 3 * spy["Volume"]).cumsum()
        / spy["Volume"].cumsum().replace(0, 1)
    )

    last = spx.iloc[-1]
    prev = spx.iloc[-2]
    spy_last = spy.iloc[-1]
    vix_last = vix.iloc[-1]["Close"]

    price = float(last["Close"])
    ema9 = float(last["EMA9"])
    ema20 = float(last["EMA20"])
    rsi = float(last["RSI"])
    spy_price = float(spy_last["Close"])
    spy_vwap = float(spy_last["VWAP"])

    high_low = spx["High"] - spx["Low"]
    high_close = (spx["High"] - spx["Close"].shift()).abs()
    low_close = (spx["Low"] - spx["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    candle_time = spx.index[-1]
    if candle_time.tzinfo is None:
        candle_time = candle_time.tz_localize("UTC")
    age = (datetime.now(timezone.utc) - candle_time.to_pydatetime()).total_seconds() / 60

    call_score = 0
    put_score = 0

    if price > ema9:
        call_score += 1
    if ema9 > ema20:
        call_score += 1
    if rsi > 50:
        call_score += 1
    if float(last["Close"]) > float(prev["Close"]):
        call_score += 1
    if spy_price > spy_vwap:
        call_score += 1

    if price < ema9:
        put_score += 1
    if ema9 < ema20:
        put_score += 1
    if rsi < 50:
        put_score += 1
    if float(last["Close"]) < float(prev["Close"]):
        put_score += 1
    if spy_price < spy_vwap:
        put_score += 1

    st.subheader("بيانات السوق")
    a, b = st.columns(2)
    a.metric("SPX", f"{price:,.2f}")
    b.metric("VIX", f"{vix_last:.2f}")

    a, b = st.columns(2)
    a.metric("RSI", f"{rsi:.1f}")
    b.metric("ATR", f"{atr:.2f}")

    st.caption(f"آخر شمعة: {candle_time.strftime('%Y-%m-%d %H:%M UTC')}")
    st.caption(f"عمر البيانات: {age:.0f} دقيقة تقريبًا")

    st.divider()
    st.subheader("نتيجة التحليل")

    if age > 20 or pd.isna(atr) or atr <= 0:
        st.error("⛔ البيانات قديمة أو غير مكتملة — لا توجد صفقة.")
    elif call_score >= 4 and call_score > put_score:
        stop = price - (atr * 1.2)
        target1 = price + (atr * 1.0)
        target2 = price + (atr * 2.0)

        st.success("🟢 إشارة CALL محتملة")
        st.metric("منطقة الدخول المرجعية على SPX", f"{price:,.2f}")
        st.metric("تأكيد الدخول", f"إغلاق شمعة 5 دقائق فوق {price:,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{stop:,.2f}")
        st.metric("الهدف الأول", f"{target1:,.2f}")
        st.metric("الهدف الثاني", f"{target2:,.2f}")
        st.write(f"قوة الشروط: {call_score}/5")

    elif put_score >= 4 and put_score > call_score:
        stop = price + (atr * 1.2)
        target1 = price - (atr * 1.0)
        target2 = price - (atr * 2.0)

        st.error("🔴 إشارة PUT محتملة")
        st.metric("منطقة الدخول المرجعية على SPX", f"{price:,.2f}")
        st.metric("تأكيد الدخول", f"إغلاق شمعة 5 دقائق تحت {price:,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{stop:,.2f}")
        st.metric("الهدف الأول", f"{target1:,.2f}")
        st.metric("الهدف الثاني", f"{target2:,.2f}")
        st.write(f"قوة الشروط: {put_score}/5")

    else:
        st.info("⏳ انتظار — شروط الدخول غير مكتملة.")
        st.write(f"قوة CALL: {call_score}/5")
        st.write(f"قوة PUT: {put_score}/5")

    st.divider()
    st.caption(
        "حجم SPY وVWAP يستخدمان كمؤشر مساعد فقط. "
        "مستويات الدخول والوقف والأهداف تخص مؤشر SPX، وليست أسعار عقود الخيارات."
    )
    st.caption("لا يوجد دخول مضمون. عقود 0DTE عالية المخاطر وقد تخسر كامل قيمتها.")

except Exception as e:
    st.error("حدث خطأ أثناء تحميل البيانات.")
    st.write(str(e))
