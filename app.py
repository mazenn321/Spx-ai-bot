
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(page_title="SPX AI Signals", page_icon="📈", layout="wide")
st.title("📈 SPX Trading Signals Pro")
st.caption("SPX + ES | 5m + 15m | CALL / PUT | دعم ومقاومة")

NY = ZoneInfo("America/New_York")
MAX_AGE = 5


@st.cache_data(ttl=20)
def get_data(symbol):
    return yf.Ticker(symbol).history(
        period="5d",
        interval="5m",
        prepost=True,
        auto_adjust=False
    )


def age_minutes(index):
    ts = index[-1]
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return (
        datetime.now(timezone.utc) -
        ts.to_pydatetime().astimezone(timezone.utc)
    ).total_seconds() / 60


def indicators(df):
    df = df.copy().dropna(subset=["Close", "High", "Low"])
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()
    return df


def trend_15m(df):
    x = df[["Open", "High", "Low", "Close"]].resample("15min").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last"
    }).dropna()

    if len(x) < 22:
        return "غير كافٍ"

    e9 = x["Close"].ewm(span=9, adjust=False).mean().iloc[-2]
    e20 = x["Close"].ewm(span=20, adjust=False).mean().iloc[-2]

    if e9 > e20:
        return "صاعد 🟢"
    if e9 < e20:
        return "هابط 🔴"
    return "محايد"


def session_status():
    now = datetime.now(NY)
    day = now.weekday()
    minute = now.hour * 60 + now.minute

    gth_evening = day in [6, 0, 1, 2, 3] and minute >= 20 * 60 + 15
    gth_morning = day in [0, 1, 2, 3, 4] and minute <= 9 * 60 + 25

    rth = day < 5 and 9 * 60 + 30 <= minute <= 16 * 60 + 15

    if rth:
        return "RTH", now
    if gth_evening or gth_morning:
        return "GTH", now
    return "CLOSED", now


def analyze(df, label):
    df = indicators(df)
    if len(df) < 30:
        st.warning(f"{label}: البيانات غير كافية.")
        return

    age = age_minutes(df.index)
    last = df.iloc[-1]
    previous = df.iloc[-2]

    price = float(last["Close"])
    atr = float(last["ATR"])
    rsi = float(last["RSI"])
    ema9 = float(last["EMA9"])
    ema20 = float(last["EMA20"])

    # مستويات آخر 20 شمعة، مع استبعاد الشمعة الحالية
    resistance = float(df["High"].iloc[-21:-1].max())
    support = float(df["Low"].iloc[-21:-1].min())

    # اتجاه 5 دقائق
    if ema9 > ema20:
        trend5 = "صاعد 🟢"
    elif ema9 < ema20:
        trend5 = "هابط 🔴"
    else:
        trend5 = "محايد"

    trend15 = trend_15m(df)

    st.subheader(f"🎯 تحليل {label}")

    a, b, c = st.columns(3)
    a.metric("السعر", f"{price:,.2f}")
    b.metric("RSI", f"{rsi:.1f}")
    c.metric("ATR", f"{atr:.2f}")

    a, b, c = st.columns(3)
    a.metric("الاتجاه 5 دقائق", trend5)
    b.metric("الاتجاه 15 دقيقة", trend15)
    c.metric("عمر البيانات", f"{age:.1f} دقيقة")

    a, b = st.columns(2)
    a.metric("الدعم", f"{support:,.2f}")
    b.metric("المقاومة", f"{resistance:,.2f}")

    if age > MAX_AGE:
        st.error(
            f"البيانات أقدم من {MAX_AGE} دقائق. "
            "تم إيقاف إشارات الدخول حفاظاً على دقة التحليل."
        )
        return

    if any(pd.isna(x) for x in [atr, rsi, ema9, ema20]) or atr <= 0:
        st.warning("المؤشرات غير مكتملة.")
        return

    # تأكيد الاختراق أو الكسر
    breakout = price > resistance
    breakdown = price < support

    call_score = sum([
        ema9 > ema20,
        rsi > 52,
        trend15 == "صاعد 🟢",
        price > float(previous["Close"]),
        breakout
    ])

    put_score = sum([
        ema9 < ema20,
        rsi < 48,
        trend15 == "هابط 🔴",
        price < float(previous["Close"]),
        breakdown
    ])

    st.write(f"تأكيد اختراق المقاومة: {'نعم' if breakout else 'لا'}")
    st.write(f"تأكيد كسر الدعم: {'نعم' if breakdown else 'لا'}")

    if call_score >= 4 and call_score > put_score and breakout:
        st.success("🟢 إشارة CALL محتملة — تأكيد اختراق")

        st.metric("الدخول بعد التأكيد", f"فوق {resistance:,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{price - atr * 1.2:,.2f}")
        st.metric("الهدف الأول", f"{price + atr:,.2f}")
        st.metric("الهدف الثاني", f"{price + atr * 2:,.2f}")
        st.write(f"قوة الشروط: {call_score}/5")
        st.toast("ظهرت إشارة CALL محتملة")

    elif put_score >= 4 and put_score > call_score and breakdown:
        st.error("🔴 إشارة PUT محتملة — تأكيد كسر")

        st.metric("الدخول بعد التأكيد", f"تحت {support:,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{price + atr * 1.2:,.2f}")
        st.metric("الهدف الأول", f"{price - atr:,.2f}")
        st.metric("الهدف الثاني", f"{price - atr * 2:,.2f}")
        st.write(f"قوة الشروط: {put_score}/5")
        st.toast("ظهرت إشارة PUT محتملة")

    else:
        st.info("⏳ انتظار — لا يوجد تأكيد دخول قوي.")
        st.write(f"قوة CALL: {call_score}/5")
        st.write(f"قوة PUT: {put_score}/5")


if st.button("🔄 تحديث البيانات والتحليل", use_container_width=True):
    st.cache_data.clear()

try:
    session, now = session_status()
    st.write(f"توقيت نيويورك: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    st.write(f"حالة التداول: **{session}**")

    # عرض SPX دائماً، حتى لو كانت آخر قراءة رسمية قديمة
    with st.spinner("تحميل بيانات SPX وES..."):
        spx = get_data("^GSPC")
        es = get_data("ES=F")
        vix = get_data("^VIX")

    if spx.empty:
        st.warning("تعذر تحميل بيانات SPX.")
    else:
        spx_age = age_minutes(spx.index)
        st.subheader("📊 مؤشر SPX النقدي")
        st.metric("آخر قراءة SPX", f"{float(spx['Close'].iloc[-1]):,.2f}")
        st.caption(
            f"آخر شمعة: {spx.index[-1]} | "
            f"عمر البيانات: {spx_age:.1f} دقيقة"
        )

    if not vix.empty:
        st.metric("VIX", f"{float(vix['Close'].iloc[-1]):.2f}")

    if session == "RTH":
        st.info("الجلسة الرسمية: التحليل الأساسي على SPX.")
        if not spx.empty:
            analyze(spx, "SPX النقدي")
        if not es.empty:
            with st.expander("عرض تحليل ES للمقارنة"):
                analyze(es, "ES Futures")

    elif session == "GTH":
        st.info(
            "جلسة ممتدة: SPX يعرض آخر قراءة رسمية، "
            "وES يستخدم لمتابعة الحركة الحالية استرشادياً."
        )
        if not es.empty:
            st.subheader("🌙 حركة ES الحالية")
            st.metric("ES Futures", f"{float(es['Close'].iloc[-1]):,.2f}")
            analyze(es, "ES Futures — استرشادي وليس SPX")

    else:
        st.warning(
            "السوق مغلق حسب جدول الجلسات المعتاد. "
            "تظهر آخر قراءة SPX وES فقط دون إشارة دخول."
        )

except Exception as e:
    st.error("حدث خطأ أثناء تحميل البيانات.")
    st.code(str(e))

st.divider()
st.caption(
    "المستويات محسوبة على الأصل الذي يظهر اسمه في عنوان التحليل. "
    "مستويات ES ليست مستويات SPX ولا أسعار عقود الخيارات. "
    "Yahoo Finance ليس بثاً مضموناً لحظياً. "
    "هذا محرك قواعد فنية وليس نموذج AI مدرباً. "
    "عقود 0DTE قد تخسر كامل قيمتها."
)
