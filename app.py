import streamlit as st
import pandas as pd
import numpy as np
import requests
from streamlit_autorefresh import st_autorefresh

# =========================================================
# MAZONI BOT | Structure + Breakout Retest
# تحليل الأصل الأساسي فقط، وليس عقود الخيارات.
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
.metric-value { color:#f4e6c3; font-size:22px; font-weight:800; }
.signal-card {
    background:linear-gradient(145deg,rgba(28,32,41,.98),rgba(12,15,21,.98));
    border:1px solid rgba(204,170,99,.42);
    border-radius:18px; padding:22px; margin:8px 0 16px;
}
.signal-call { color:#35d39a; font-size:32px; font-weight:900; }
.signal-put { color:#ff6b75; font-size:32px; font-weight:900; }
.signal-wait { color:#e3c477; font-size:32px; font-weight:900; }
.small-note { color:#a9a39a; font-size:12px; }
div.stButton > button {
    border:1px solid #c9a65c; color:#e7d19b;
    background:#171a20; border-radius:10px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="mazoni-title">👑 MAZONI BOT</div>', unsafe_allow_html=True)
st.markdown('<div class="mazoni-sub">SMART MARKET LEVELS · STRUCTURE & RETEST</div>', unsafe_allow_html=True)

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
    if isinstance(data, dict) and isinstance(data.get("quote"), dict):
        data = data["quote"]
    return data


def get_candles(symbol, interval, limit=250):
    data = get_json(
        f"{API_BASE}/{symbol}/ohlc",
        params={"interval": interval, "limit": limit}
    )
    bars = data.get("bars", []) if isinstance(data, dict) else data
    if not isinstance(bars, list) or not bars:
        raise ValueError(f"لا توجد شموع للفريم {interval}")

    df = pd.DataFrame(bars)
    required = ["openTime", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"حقول الشموع ناقصة: {', '.join(missing)}")

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    parsed = pd.to_datetime(df["openTime"], utc=True, errors="coerce")
    if parsed.isna().all():
        raw = pd.to_numeric(df["openTime"], errors="coerce")
        valid = raw.dropna()
        if not valid.empty:
            unit = "ms" if valid.median() > 10**11 else "s"
            parsed = pd.to_datetime(raw, unit=unit, utc=True, errors="coerce")

    df["time"] = parsed
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)

    if "isOpen" in df.columns:
        opened = df["isOpen"].astype(str).str.lower().isin(["true", "1", "yes"])
        df = df.loc[~opened].copy()

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


# ------------------------- MARKET STRUCTURE -------------------------
def empty_signal(reason, support=np.nan, resistance=np.nan):
    return {
        "side": "WAIT", "plan_side": "WAIT", "confirmed": False,
        "reason": reason, "score": 0,
        "entry_low": np.nan, "entry_high": np.nan,
        "stop": np.nan, "targets": [np.nan, np.nan, np.nan],
        "support": support, "resistance": resistance,
        "volume_note": "لا تتوفر بيانات حجم كافية",
        "setup": "لا يوجد إعداد واضح"
    }


def collect_swing_levels(df, side, above_price=None, below_price=None):
    """Extract simple confirmed local swing levels from historical candles."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    levels = []
    for i in range(2, len(df) - 2):
        if side == "CALL":
            is_swing = highs[i] >= max(highs[i-2:i+3])
            level = float(highs[i])
            if is_swing and above_price is not None and level > above_price:
                levels.append(level)
        else:
            is_swing = lows[i] <= min(lows[i-2:i+3])
            level = float(lows[i])
            if is_swing and below_price is not None and level < below_price:
                levels.append(level)
    return sorted(set(levels)) if side == "CALL" else sorted(set(levels), reverse=True)


def make_signal(a4, a15, a5, live_price):
    d15 = a15["df"]
    d5 = a5["df"]
    last5 = d5.iloc[-1]
    atr = a5["atr"]

    if not np.isfinite(atr) or atr <= 0 or len(d5) < 35 or len(d15) < 35:
        return empty_signal("البيانات أو متوسط الحركة غير كافية لبناء سيناريو موثوق")

    # المستويات المرجعية من 15 دقيقة، مع استبعاد آخر شمعة لتجنب تحريك المستوى معها.
    ref15 = d15.iloc[-31:-1]
    resistance = float(ref15["high"].max())
    support = float(ref15["low"].min())

    # لا نختار اتجاهاً افتراضياً عند اختلاف الفريمات.
    bias_up = a4["trend_value"] == 1 and a15["trend_value"] == 1
    bias_down = a4["trend_value"] == -1 and a15["trend_value"] == -1

    if not bias_up and not bias_down:
        return empty_signal(
            "اتجاه 4 ساعات و15 دقيقة غير متوافق؛ لا نرجّح CALL أو PUT بالتخمين.",
            support, resistance
        )

    side = "CALL" if bias_up else "PUT"
    entry_level = resistance if side == "CALL" else support

    # نبحث عن اختراق المستوى خلال آخر 6 شموع مغلقة، ثم إعادة اختباره في آخر شمعة.
    recent = d5.iloc[-7:-1]
    if side == "CALL":
        broke = bool((recent["close"] > entry_level).any())
        retested = bool(
            last5["low"] <= entry_level + 0.12 * atr
            and last5["close"] > entry_level
            and last5["close"] > last5["open"]
        )
        momentum_ok = a5["macd"] > a5["macd_signal"] and 50 <= a5["rsi"] <= 72
        invalidated = live_price < entry_level - 0.35 * atr
    else:
        broke = bool((recent["close"] < entry_level).any())
        retested = bool(
            last5["high"] >= entry_level - 0.12 * atr
            and last5["close"] < entry_level
            and last5["close"] < last5["open"]
        )
        momentum_ok = a5["macd"] < a5["macd_signal"] and 28 <= a5["rsi"] <= 50
        invalidated = live_price > entry_level + 0.35 * atr

    # الحجم تأكيدي فقط إذا كان المصدر يوفّره؛ لا نرفض الإعداد بسبب غياب الحجم.
    volume_available = (
        "volume" in d5.columns
        and pd.notna(last5.get("vol_avg20"))
        and last5["vol_avg20"] > 0
        and pd.notna(last5.get("volume"))
    )
    volume_ok = True
    if volume_available:
        volume_ok = bool(last5["volume"] >= last5["vol_avg20"] * 0.90)
        volume_note = (
            "الحجم يدعم الحركة" if volume_ok
            else "الحجم أضعف من المتوسط؛ التأكيد غير مكتمل"
        )
    else:
        volume_note = "الحجم غير متاح؛ لم يُستخدم كشرط"

    if invalidated:
        return empty_signal(
            "السعر عاد خلف مستوى الاختراق/الكسر؛ أُلغي الإعداد الحالي.",
            support, resistance
        )

    # منطقة المراقبة حول المستوى الفني، وليست أمراً تلقائياً.
    tolerance = 0.10 * atr
    entry_low = entry_level - tolerance
    entry_high = entry_level + tolerance

    # وقف خلف قاع/قمة إعادة الاختبار مع هامش صغير.
    recent5 = d5.iloc[-5:]
    if side == "CALL":
        stop = float(recent5["low"].min() - 0.15 * atr)
        risk = max(entry_level - stop, 0.25 * atr)
        targets = [entry_level + risk, entry_level + 2 * risk, entry_level + 3 * risk]
        swing_targets = collect_swing_levels(d15.iloc[:-1], "CALL", above_price=entry_level)
    else:
        stop = float(recent5["high"].max() + 0.15 * atr)
        risk = max(stop - entry_level, 0.25 * atr)
        targets = [entry_level - risk, entry_level - 2 * risk, entry_level - 3 * risk]
        swing_targets = collect_swing_levels(d15.iloc[:-1], "PUT", below_price=entry_level)

    # استخدم مستويات القمم/القيعان التاريخية إذا توفرت، وإلا تبقى أهداف R واضحة.
    for i, level in enumerate(swing_targets[:3]):
        if side == "CALL" and level > entry_level:
            targets[i] = min(targets[i], level) if targets[i] > entry_level else level
        elif side == "PUT" and level < entry_level:
            targets[i] = max(targets[i], level) if targets[i] < entry_level else level

    aligned_5m = a5["trend_value"] == (1 if side == "CALL" else -1)
    confirmed = broke and retested and momentum_ok and aligned_5m and volume_ok

    if confirmed:
        reason = (
            "توافق اتجاه 4 ساعات و15 دقيقة، ثم اختراق وإعادة اختبار ناجحة "
            "على 5 دقائق مع زخم مؤيد."
        )
        score = 90 if volume_available else 85
        setup = "اختراق + إعادة اختبار مؤكدة فنياً"
    else:
        missing = []
        if not broke:
            missing.append("لم يحدث اختراق/كسر واضح")
        elif not retested:
            missing.append("لم تكتمل إعادة الاختبار")
        if not aligned_5m:
            missing.append("اتجاه 5 دقائق لم يؤكد")
        if not momentum_ok:
            missing.append("الزخم أو RSI غير مؤيد")
        if not volume_ok:
            missing.append("الحجم لا يؤكد")
        reason = "اتجاه عام " + ("صاعد" if side == "CALL" else "هابط") + "، لكن " + "، ".join(missing) + "."
        score = 55 + (10 if broke else 0) + (10 if retested else 0) + (10 if momentum_ok else 0) + (5 if aligned_5m else 0)
        setup = "منطقة مراقبة فقط — لا دخول حتى اكتمال التأكيد"

    return {
        "side": side if confirmed else "WAIT",
        "plan_side": side,
        "confirmed": confirmed,
        "reason": reason,
        "score": min(score, 95) if confirmed else min(score, 79),
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop": stop,
        "targets": targets,
        "support": support,
        "resistance": resistance,
        "volume_note": volume_note,
        "setup": setup,
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
st.sidebar.caption("الفريمات: 4 ساعات للاتجاه / 15 دقيقة للمستويات / 5 دقائق للتفعيل")
st.sidebar.caption("تحديث تلقائي كل 15 ثانية")
st.sidebar.caption("البيانات تعتمد على دعم مزود الخدمة للرمز المطلوب.")

# ------------------------- MAIN -------------------------
st.markdown(f"### تحليل الأصل: `{selected_symbol}`")
st.caption("المستويات المعروضة تخص الأصل المختار نفسه، ولا تمثل سعر عقد الخيارات.")

try:
    used_symbol = selected_symbol
    fallback_used = False

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

    fresh = not stale
    if quote_age is not None:
        try:
            fresh = fresh and float(quote_age) <= 60
        except Exception:
            pass
    if not fresh:
        signal["side"] = "WAIT"
        signal["confirmed"] = False
        signal["reason"] = "السعر قديم أو البيانات معلّمة بأنها غير محدثة؛ انتظر تحديث البيانات."
    if market_state not in ["open", "regular", "trading", "غير معروف"]:
        signal["side"] = "WAIT"
        signal["confirmed"] = False
        signal["reason"] = f"حالة السوق: {quote.get('marketState')} — لا توجد إشارة دخول جديدة."

    if fallback_used:
        st.warning(
            "تعذر جلب SPX؛ المعروض الآن US500 كبديل. "
            "جميع المستويات أدناه تخص US500 وليست مستويات SPX."
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
    side_ar = "إشارة CALL مؤكدة فنياً" if side == "CALL" else "إشارة PUT مؤكدة فنياً" if side == "PUT" else "انتظار — لا يوجد دخول الآن"
    st.markdown(
        f'<div class="signal-card"><div class="{side_class}">{side_ar}</div>'
        f'<div style="color:#d7d0c2;margin-top:8px">{signal["reason"]}</div>'
        f'<div style="color:#b9a77e;margin-top:12px">تقييم اكتمال الشروط: {signal["score"]}/100</div>'
        f'<div style="color:#b9a77e;margin-top:6px">{signal["setup"]}</div></div>',
        unsafe_allow_html=True
    )

    if signal["plan_side"] == "WAIT":
        st.info("لا يوجد سيناريو صاعد أو هابط صالح حالياً؛ لأن اتجاه 4 ساعات و15 دقيقة غير متوافق.")
    elif side == "WAIT":
        scenario_ar = "صاعد" if signal["plan_side"] == "CALL" else "هابط"
        st.info(
            f"السيناريو {scenario_ar} للمراقبة فقط. منطقة السعر أدناه مرتبطة بمستوى فني؛ "
            "لا تعتبر دخولاً قبل ظهور إشارة التأكيد."
        )

    p1, p2, p3 = st.columns(3)
    with p1:
        label = f"منطقة المراقبة/الدخول · {signal['plan_side']}" if signal["plan_side"] != "WAIT" else "منطقة الدخول"
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{fmt(signal["entry_low"])} – {fmt(signal["entry_high"])}</div></div>', unsafe_allow_html=True)
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

    st.markdown("### مستويات السوق")
    s1, s2 = st.columns(2)
    s1.metric("الدعم المرجعي · 15m", fmt(signal["support"]))
    s2.metric("المقاومة المرجعية · 15m", fmt(signal["resistance"]))
    st.caption(signal["volume_note"])

    st.markdown("### المؤشرات الفنية")
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("RSI · 5m", fmt(a5["rsi"]))
    i2.metric("ATR · 5m", fmt(a5["atr"]))
    i3.metric("EMA 20 · 5m", fmt(a5["ema20"]))
    i4.metric("EMA 50 · 5m", fmt(a5["ema50"]))

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
        "قد لا يدعم المزود جميع الأسهم أو رمز SPX. تحقق من دعم الرمز والفريمات."
    )
    st.caption(str(e))
except Exception as e:
    st.error(f"تعذر تحميل التحليل: {e}")
    st.info(
        "تأكد من أن مزود البيانات يدعم الرمز والفريمات المطلوبة، "
        "وأن استجابة الشموع تحتوي openTime وopen وhigh وlow وclose."
    )

st.markdown("---")
st.markdown(
    '<div class="small-note">MAZONI BOT أداة تحليل فني وليست توصية مالية. '
    'المستويات تخص المؤشر أو السهم الأساسي، ولا تمثل أسعار عقود الخيارات. '
    'تقييم الشروط ليس نسبة نجاح مثبتة. تحقق من السعر والتنفيذ لدى وسيطك قبل التداول.</div>',
    unsafe_allow_html=True
)
