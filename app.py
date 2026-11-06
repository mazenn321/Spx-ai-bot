
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(page_title="SPX Trading Signals", page_icon="📈")
st.title("📈 SPX Trading Signals")
st.caption("تحليل SPX وES | عقود SPX 0DTE")

st.warning(
    "مصدر البيانات Yahoo Finance وليس بثاً مضموناً لحظياً. "
    "تحقق من أسعار دراية قبل أي صفقة. "
    "الإشارات احتمالية وليست توصيات مضمونة."
)

NY = ZoneInfo("America/New_York")


@st.cache_data(ttl=30)
def get_data(symbol, extended=False):
    return yf.Ticker(symbol).history(
        period="5d",
        interval="5m",
        prepost=extended,
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


def rsi_calc(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_indicators(df):
    df = df.copy().dropna(
        subset=["Close", "High", "Low"]
    )
    df["EMA9"] = df["Close"].ewm(
        span=9, adjust=False
    ).mean()
    df["EMA20"] = df["Close"].ewm(
        span=20, adjust=False
    ).mean()
    df["RSI"] = rsi_calc(df["Close"])

    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()
    return df


def get_session():
    now = datetime.now(NY)
    weekday = now.weekday()
    minutes = now.hour * 60 + now.minute

    # جلسة Cboe GTH: من الأحد إلى الخميس مساءً
    # وتمتد إلى صباح يوم العمل التالي
    gth_evening = (
        weekday in [6, 0, 1, 2, 3]
        and minutes >= 20 * 60 + 15
    )
    gth_morning = (
        weekday in [0, 1, 2, 3, 4]
        and minutes <= 9 * 60 + 25
    )

    rth = (
        weekday < 5
        and 9 * 60 + 30 <= minutes <= 16 * 60 + 15
    )

    if gth_evening or gth_morning:
        return now, "GTH"
    if rth:
        return now, "RTH"
    return now, "CLOSED"


def show_signal(df, label, age, max_age=15):
    st.subheader("🎯 نتيجة التحليل")
    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["Close"])
    ema9 = float(last["EMA9"])
    ema20 = float(last["EMA20"])
    rsi = float(last["RSI"])
    atr = float(last["ATR"])

    if age > max_age:
        st.error(
            f"البيانات قديمة ({age:.0f} دقيقة). "
            "لن نصدر إشارة."
        )
        return

    if any(pd.isna(x) for x in [ema9, ema20, rsi, atr]) or atr <= 0:
        st.error("المؤشرات غير مكتملة. لا توجد صفقة.")
        return

    call_score = sum([
        price > ema9,
        ema9 > ema20,
        rsi > 50,
        price > float(prev["Close"]),
        float(last["Close"]) > float(last["Open"])
    ])

    put_score = sum([
        price < ema9,
        ema9 < ema20,
        rsi < 50,
        price < float(prev["Close"]),
        float(last["Close"]) < float(last["Open"])
    ])

    st.write(f"مصدر الإشارة: **{label}**")
    st.metric("السعر المرجعي", f"{price:,.2f}")
    st.metric("RSI", f"{rsi:.1f}")
    st.metric("ATR", f"{atr:.2f}")

    if call_score >= 4 and call_score > put_score:
        st.success("🟢 CALL محتملة")
        st.metric("مستوى التأكيد", f"{float(last['High']):,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{price - atr * 1.2:,.2f}")
        st.metric("الهدف الأول", f"{price + atr:,.2f}")
        st.metric("الهدف الثاني", f"{price + atr * 2:,.2f}")
        st.write(f"قوة الشروط: {call_score}/5")

    elif put_score >= 4 and put_score > call_score:
        st.error("🔴 PUT محتملة")
        st.metric("مستوى التأكيد", f"{float(last['Low']):,.2f}")
        st.metric("وقف الخسارة المرجعي", f"{price + atr * 1.2:,.2f}")
        st.metric("الهدف الأول", f"{price - atr:,.2f}")
        st.metric("الهدف الثاني", f"{price - atr * 2:,.2f}")
        st.write(f"قوة الشروط: {put_score}/5")

    else:
        st.info("⏳ انتظار — شروط الدخول غير مكتملة.")
        st.write(f"قوة CALL: {call_score}/5")
        st.write(f"قوة PUT: {put_score}/5")


if st.button("🔄 تحديث التحليل", use_container_width=True):
    st.cache_data.clear()

try:
    now, session = get_session()
    st.caption(f"توقيت نيويورك: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    st.caption(f"حالة الجلسة: {session}")

    if session == "CLOSED":
        st.info("جلسة تداول SPX مغلقة حالياً حسب الجدول المعتاد.")
        st.stop()

    if session == "GTH":
        st.subheader("🌙 جلسة التداول الممتدة GTH")
        with st.spinner("جاري تحميل بيانات ES..."):
            es = get_data("ES=F", extended=True)

        if es.empty or len(es) < 30:
            st.error("تعذر تحميل بيانات ES أو أنها غير كافية.")
            st.stop()

        es = add_indicators(es)
        age = age_minutes(es.index)

        st.metric("ES Futures", f"{float(es['Close'].iloc[-1]):,.2f}")
        st.caption(
            f"آخر شمعة ES: {es.index[-1].strftime('%Y-%m-%d %H:%M %Z')}"
        )
        st.caption(f"عمر بيانات ES: {age:.0f} دقيقة")

        show_signal(
            es,
            "ES Futures — مؤشر استرشادي لحركة SPX",
            age
        )

        st.warning(
            "هذه مستويات ES وليست مستويات SPX. "
            "لا تحولها مباشرة إلى سعر SPX أو سعر عقد الخيارات. "
            "قيمة مؤشر SPX النقدي قد لا تكون محدثة خلال GTH."
        )

    elif session == "RTH":
        st.subheader("☀️ الجلسة الرسمية RTH")
        with st.spinner("جاري تحميل بيانات SPX وSPY وVIX..."):
            spx = get_data("^GSPC")
            spy = get_data("SPY")
            vix = get_data("^VIX")

        if spx.empty or spy.empty or vix.empty:
            st.error("تعذر تحميل إحدى بيانات السوق.")
            st.stop()

        spx = add_indicators(spx)
        spy = spy.dropna(
            subset=["Close", "High", "Low", "Volume"]
        )
        vix = vix.dropna(subset=["Close"])

        if len(spx) < 30 or len(spy) < 10 or len(vix) < 2:
            st.error("البيانات غير كافية.")
            st.stop()

        typical = (spy["High"] + spy["Low"] + spy["Close"]) / 3
        dates = pd.Series(spy.index.date, index=spy.index)
        volume_price = typical * spy["Volume"]

        spy["VWAP"] = (
            volume_price.groupby(dates).cumsum()
            / spy["Volume"].groupby(dates).cumsum().replace(0, np.nan)
        )

        spx_age = age_minutes(spx.index)
        spy_age = age_minutes(spy.index)
        vix_age = age_minutes(vix.index)

        st.metric("SPX", f"{float(spx['Close'].iloc[-1]):,.2f}")
        st.metric("VIX", f"{float(vix['Close'].iloc[-1]):.2f}")
        st.caption(f"عمر SPX: {spx_age:.0f} دقيقة")
        st.caption(f"عمر SPY: {spy_age:.0f} دقيقة")
        st.caption(f"عمر VIX: {vix_age:.0f} دقيقة")

        if max(spx_age, spy_age, vix_age) > 15:
            st.error("البيانات قديمة. لن نصدر إشارة.")
            st.stop()

        show_signal(
            spx,
            "SPX النقدي",
            spx_age
        )

        st.caption(
            "VWAP وحجم SPY مؤشرات مساعدة وليست بيانات حجم SPX."
        )

except Exception as e:
    st.error("حدث خطأ أثناء تحميل أو تحليل البيانات.")
    st.code(str(e))

st.divider()
st.caption(
    "هذا محرك قواعد فنية وليس نموذج ذكاء اصطناعي مدرباً. "
    "إشاراته ليست مضمونة، وعقود 0DTE قد تخسر كامل قيمتها."
)
