
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="SPX AI Signals",
    page_icon="📈",
    layout="centered"
)

st.title("📈 SPX Trading Signals")
st.caption("تحليل فني لمؤشر SPX | عقود 0DTE")

st.warning(
    "البيانات من Yahoo Finance وليست بثاً مضموناً لحظياً. "
    "تحقق من السعر في دراية قبل أي صفقة. "
    "هذا محرك قواعد فنية وليس نموذج ذكاء اصطناعي مدرباً."
)

NY = ZoneInfo("America/New_York")

@st.cache_data(ttl=30)
def get_data(symbol):
    return yf.Ticker(symbol).history(
        period="5d",
        interval="5m",
        prepost=False,
        auto_adjust=False
    )

def rsi_calc(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def market_status():
    now = datetime.now(NY)
    is_weekday = now.weekday() < 5
    is_session = (
        now.hour > 9 or (now.hour == 9 and now.minute >= 30)
    ) and (
        now.hour < 16
    )
    return now, is_weekday and is_session

def age_minutes(index):
    timestamp = index[-1]
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return (
        datetime.now(timezone.utc) -
        timestamp.to_pydatetime().astimezone(timezone.utc)
    ).total_seconds() / 60

if st.button("🔄 تحديث التحليل", use_container_width=True):
    st.cache_data.clear()

try:
    with st.spinner("جاري تحميل بيانات السوق..."):
        spx = get_data("^GSPC")
        spy = get_data("SPY")
        vix = get_data("^VIX")

    if spx.empty or spy.empty or vix.empty:
        st.error("تعذر تحميل البيانات من المصدر.")
        st.stop()

    spx = spx.dropna(subset=["Close", "High", "Low"])
    spy = spy.dropna(subset=["Close", "High", "Low", "Volume"])
    vix = vix.dropna(subset=["Close"])

    if len(spx) < 30 or len(spy) < 10 or len(vix) < 2:
        st.error("البيانات غير كافية لحساب المؤشرات.")
        st.stop()

    spx["EMA9"] = spx["Close"].ewm(span=9, adjust=False).mean()
    spx["EMA20"] = spx["Close"].ewm(span=20, adjust=False).mean()
    spx["RSI"] = rsi_calc(spx["Close"])

    typical = (spy["High"] + spy["Low"] + spy["Close"]) / 3
    session_dates = pd.Series(
        spy.index.date, index=spy.index
    )
    volume_price = typical * spy["Volume"]

    spy["VWAP"] = (
        volume_price.groupby(session_dates).cumsum()
        / spy["Volume"].groupby(session_dates).cumsum().replace(0, np.nan)
    )

    high_low = spx["High"] - spx["Low"]
    high_close = (spx["High"] - spx["Close"].shift()).abs()
    low_close = (spx["Low"] - spx["Close"].shift()).abs()

    true_range = pd.concat(
        [high_low, high_close, low_close], axis=1
    ).max(axis=1)

    spx["ATR"] = true_range.rolling(14).mean()

    last = spx.iloc[-1]
    prev = spx.iloc[-2]
    spy_last = spy.iloc[-1]
    vix_last = vix.iloc[-1]

    price = float(last["Close"])
    ema9 = float(last["EMA9"])
    ema20 = float(last["EMA20"])
    rsi = float(last["RSI"])
    atr = float(last["ATR"])
    spy_price = float(spy_last["Close"])
    spy_vwap = float(spy_last["VWAP"])
    vix_price = float(vix_last["Close"])

    spx_age = age_minutes(spx.index)
    spy_age = age_minutes(spy.index)
    vix_age = age_minutes(vix.index)

    now, market_open = market_status()

    st.subheader("📊 بيانات السوق")

    a, b = st.columns(2)
    a.metric("SPX", f"{price:,.2f}")
    b.metric("VIX", f"{vix_price:.2f}")

    a, b = st.columns(2)
    a.metric("RSI", f"{rsi:.1f}")
    b.metric("ATR", f"{atr:.2f}")

    st.caption(
        f"آخر شمعة SPX: {spx.index[-1].strftime('%Y-%m-%d %H:%M %Z')}"
    )
    st.caption(f"عمر بيانات SPX: {spx_age:.0f} دقيقة")
    st.caption(f"عمر بيانات SPY: {spy_age:.0f} دقيقة")
    st.caption(f"عمر بيانات VIX: {vix_age:.0f} دقيقة")
    st.caption(f"توقيت نيويورك: {now.strftime('%H:%M:%S')}")

    st.divider()
    st.subheader("🎯 نتيجة التحليل")

    call_score = 0
    put_score = 0

    if price > ema9:
        call_score += 1
    if ema9 > ema20:
        call_score += 1
    if rsi > 50:
        call_score += 1
    if price > float(prev["Close"]):
        call_score += 1
    if spy_price > spy_vwap:
        call_score += 1

    if price < ema9:
        put_score += 1
    if ema9 < ema20:
        put_score += 1
    if rsi < 50:
        put_score += 1
    if price < float(prev["Close"]):
        put_score += 1
    if spy_price < spy_vwap:
        put_score += 1

    if not market_open:
        st.info(
            "السوق الأمريكي مغلق حسب جدول التداول المعتاد. "
            "لا توجد إشارة دخول جديدة."
        )

    elif max(spx_age, spy_age, vix_age) > 15:
        st.error(
            "⛔ البيانات قديمة أو متأخرة. "
            "لن نصدر إشارة حتى تتحدث البيانات."
        )

    elif pd.isna(atr) or pd.isna(rsi) or pd.isna(spy_vwap) or atr <= 0:
        st.error("المؤشرات غير مكتملة. لا توجد صفقة.")

    elif call_score >= 4 and call_score > put_score:
        stop = price - (atr * 1.2)
        target1 = price + atr
        target2 = price + (atr * 2)
        trigger = float(last["High"])

        st.success("🟢 CALL محتملة")
        st.metric("مستوى المؤشر المرجعي", f"{price:,.2f}")
        st.metric("مستوى تأكيد الاختراق", f"{trigger:,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{stop:,.2f}")
        st.metric("الهدف الأول", f"{target1:,.2f}")
        st.metric("الهدف الثاني", f"{target2:,.2f}")
        st.write(f"قوة الشروط: {call_score}/5")
        st.caption("انتظر تأكيد حركة السعر ولا تدخل لمجرد ظهور الإشارة.")

    elif put_score >= 4 and put_score > call_score:
        stop = price + (atr * 1.2)
        target1 = price - atr
        target2 = price - (atr * 2)
        trigger = float(last["Low"])

        st.error("🔴 PUT محتملة")
        st.metric("مستوى المؤشر المرجعي", f"{price:,.2f}")
        st.metric("مستوى تأكيد الكسر", f"{trigger:,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{stop:,.2f}")
        st.metric("الهدف الأول", f"{target1:,.2f}")
        st.metric("الهدف الثاني", f"{target2:,.2f}")
        st.write(f"قوة الشروط: {put_score}/5")
        st.caption("انتظر تأكيد حركة السعر ولا تدخل لمجرد ظهور الإشارة.")

    else:
        st.info("⏳ انتظار — شروط الدخول غير مكتملة.")
        st.write(f"قوة CALL: {call_score}/5")
        st.write(f"قوة PUT: {put_score}/5")

    st.divider()
    st.caption(
        "المستويات تخص مؤشر SPX وليست أسعار عقود الخيارات. "
        "VWAP وحجم SPY مؤشرات مساعدة وليست بيانات حجم SPX."
    )
    st.caption(
        "لا يوجد دخول مضمون. عقود 0DTE عالية المخاطر "
        "وقد تخسر كامل قيمة العقد."
    )

except Exception as e:
    st.error("حدث خطأ أثناء تحميل أو تحليل البيانات.")
    st.code(str(e))
