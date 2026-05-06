# UNIFIED PRO TRADING DASHBOARD - HIGH SPEED LITE VERSION
# (SMC ONLY | EURUSD & XAUUSD)
from streamlit.runtime.scriptrunner import add_script_run_ctx
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from pathlib import Path
from datetime import date, datetime
import requests
from streamlit_autorefresh import st_autorefresh
import concurrent.futures

st.set_page_config(
    page_title="SMC Lite Dashboard",
    page_icon="⚡",
    layout="wide"
)

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="refresh")

# =====================================================
# CONFIG & TELEGRAM
# =====================================================

BOT_TOKEN = "8775932132:AAFQUiigqXKQuNHbEF9w86pyj-SJK2-f5Rs"
CHAT_ID = "@yimsondev"
# 8512166732

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
JOURNAL_FILE = DATA_DIR / "unified_trading_journal.csv"

# ONLY 2 PAIRS FOR MAXIMUM SPEED
PAIRS = {
    "EURUSD": {"ticker": "EURUSD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 1.10000},
    "XAUUSD": {"ticker": "GC=F", "pip": 0.01, "contract": 100, "decimals": 2, "default": 2350.00},
}

RR_OPTIONS = {
    "1:1": 1.0, "1:1.5": 1.5, "1:2": 2.0,
    "1:2.5": 2.5, "1:3": 3.0, "1:4": 4.0,
}

JOURNAL_COLUMNS = [
    "Trade_ID", "Date", "Strategy", "Market", "Direction", "Signal", "Session",
    "Entry", "Stop_Loss", "Take_Profit", "Risk_Percent", "Risk_Amount",
    "Lot_Size", "Position_Size", "Risk_Reward", "Result", "Exit_Price",
    "Exit_Reason", "PnL", "R_Multiple", "Emotion", "Mistake", "Notes"
]

BUY_BG, SELL_BG, NEUTRAL_BG = "#dcfce7", "#fee2e2", "#ffedd5"

# =====================================================
# CSS
# =====================================================

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
.main-title { font-size: 34px; font-weight: 900; color: #0f172a; margin-bottom: 0.2rem; }
.subtitle { color: #64748b; font-size: 15px; margin-bottom: 1rem; }
.stButton > button { border-radius: 12px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# =====================================================
# CORE FUNCTIONS
# =====================================================

def send_alert(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

def price_fmt(market): return f"%.{PAIRS[market]['decimals']}f"

def fmt_price(market, value):
    if value is None or pd.isna(value): return "N/A"
    return f"{float(value):.{PAIRS[market]['decimals']}f}"

def price_step(market):
    if market == "XAUUSD": return 0.01
    return 0.0001

def clean_data(raw):
    if raw is None or raw.empty: return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
    df = raw.reset_index()
    if "Datetime" in df.columns: df.rename(columns={"Datetime": "Date"}, inplace=True)
    if "Date" not in df.columns: df.rename(columns={df.columns[0]: "Date"}, inplace=True)
    if "Volume" not in df.columns: df["Volume"] = 0
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert(None)
    for c in ["Open", "High", "Low", "Close"]: df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    df = df[(df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    return df.sort_values("Date").reset_index(drop=True)

@st.cache_data(ttl=600)
def load_market_data(market, daily_start):
    ticker = PAIRS[market]["ticker"]
    daily_raw = yf.download(ticker, start=daily_start, interval="1d", progress=False, auto_adjust=False)
    h1_raw = yf.download(ticker, period="60d", interval="1h", progress=False, auto_adjust=False)
    m15_raw = yf.download(ticker, period="30d", interval="15m", progress=False, auto_adjust=False)
    return clean_data(daily_raw), clean_data(h1_raw), clean_data(m15_raw)

def add_cameroon_time(df, start_hour, end_hour):
    df = df.copy()
    local = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert("Africa/Douala")
    df["Cameroon_Time"] = local.dt.strftime("%Y-%m-%d %H:%M")
    hour = local.dt.hour + local.dt.minute / 60
    if start_hour < end_hour: df["Trading_Window"] = (hour >= start_hour) & (hour < end_hour)
    else: df["Trading_Window"] = (hour >= start_hour) | (hour < end_hour)
    return df

def load_journal():
    if JOURNAL_FILE.exists():
        df = pd.read_csv(JOURNAL_FILE)
        for c in JOURNAL_COLUMNS:
            if c not in df.columns: df[c] = np.nan
        return df[JOURNAL_COLUMNS]
    return pd.DataFrame(columns=JOURNAL_COLUMNS)

# =====================================================
# INDICATORS & SMC LOGIC
# =====================================================

def add_atr(df, period=14):
    df = df.copy()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - df["Close"].shift()).abs(), (df["Low"] - df["Close"].shift()).abs()], axis=1).max(axis=1)
    df[f"ATR_{period}"] = tr.rolling(period).mean()
    return df

def add_ema(df):
    df = df.copy()
    for s in [9, 21, 50, 200]: df[f"EMA_{s}"] = df["Close"].ewm(span=s, adjust=False).mean()
    return df

def add_swings(df, n):
    df = df.copy()
    df["Swing_High"] = df["Swing_Low"] = np.nan
    if len(df) < n * 2 + 1:
        df["Last_Swing_High"] = df["Last_Swing_Low"] = np.nan
        return df

    for i in range(n, len(df) - n):
        if df["High"].iloc[i] == df["High"].iloc[i-n:i+n+1].max(): df.loc[df.index[i], "Swing_High"] = df["High"].iloc[i]
        if df["Low"].iloc[i] == df["Low"].iloc[i-n:i+n+1].min(): df.loc[df.index[i], "Swing_Low"] = df["Low"].iloc[i]

    df["Last_Swing_High"] = df["Swing_High"].ffill()
    df["Last_Swing_Low"] = df["Swing_Low"].ffill()
    return df

def add_smc_structure(df):
    df = df.copy()
    prev_high = df["Last_Swing_High"].shift(1)
    prev_low = df["Last_Swing_Low"].shift(1)

    df["BOS_Bullish"] = (df["Close"] > prev_high) & prev_high.notna()
    df["BOS_Bearish"] = (df["Close"] < prev_low) & prev_low.notna()

    df["Structure"] = "Neutral"
    state = "Neutral"
    for i in range(len(df)):
        if bool(df["BOS_Bullish"].iloc[i]): state = "Bullish"
        elif bool(df["BOS_Bearish"].iloc[i]): state = "Bearish"
        df.loc[df.index[i], "Structure"] = state

    df["CHOCH_Bullish"] = (df["Structure"].shift(1) == "Bearish") & (df["Structure"] == "Bullish")
    df["CHOCH_Bearish"] = (df["Structure"].shift(1) == "Bullish") & (df["Structure"] == "Bearish")
    df["Sell_Side_Sweep"] = (df["Low"] < prev_low) & (df["Close"] > prev_low) & prev_low.notna()
    df["Buy_Side_Sweep"] = (df["High"] > prev_high) & (df["Close"] < prev_high) & prev_high.notna()
    return df

def prep_smc(df, swing_len):
    df = add_atr(add_ema(add_swings(df, swing_len)))
    df = add_smc_structure(df)
    df["Equilibrium"] = (df["Last_Swing_High"] + df["Last_Swing_Low"]) / 2
    df["Premium_Discount"] = "Neutral"
    df.loc[df["Close"] < df["Equilibrium"], "Premium_Discount"] = "Discount"
    df.loc[df["Close"] > df["Equilibrium"], "Premium_Discount"] = "Premium"
    return df

def build_smc_strategy(daily, h1, m15, rr, atr_mult, swing_len, strict_mode, start_hour, end_hour, enforce_window):
    daily = prep_smc(daily, swing_len)
    h1 = prep_smc(h1, swing_len)
    m15 = prep_smc(m15, swing_len)

    daily["Daily_Bias"] = daily["Structure"].shift(1).fillna("Neutral")
    h1["H1_Structure"] = h1["Structure"].shift(1).fillna("Neutral")

    daily_state = daily[["Date", "Daily_Bias"]].dropna().sort_values("Date")
    h1_state = h1[["Date", "H1_Structure"]].dropna().sort_values("Date")
    m15 = m15.sort_values("Date").reset_index(drop=True)

    if not daily_state.empty: m15 = pd.merge_asof(m15, daily_state, on="Date", direction="backward")
    else: m15["Daily_Bias"] = "Neutral"

    if not h1_state.empty: m15 = pd.merge_asof(m15, h1_state, on="Date", direction="backward")
    else: m15["H1_Structure"] = "Neutral"

    bullish_trigger = m15["Sell_Side_Sweep"] | m15["CHOCH_Bullish"] | m15["BOS_Bullish"]
    bearish_trigger = m15["Buy_Side_Sweep"] | m15["CHOCH_Bearish"] | m15["BOS_Bearish"]

    if strict_mode:
        buy = (m15["Daily_Bias"] == "Bullish") & (m15["H1_Structure"] == "Bullish") & bullish_trigger & (m15["Premium_Discount"] == "Discount")
        sell = (m15["Daily_Bias"] == "Bearish") & (m15["H1_Structure"] == "Bearish") & bearish_trigger & (m15["Premium_Discount"] == "Premium")
    else:
        buy = (m15["H1_Structure"] == "Bullish") & bullish_trigger
        sell = (m15["H1_Structure"] == "Bearish") & bearish_trigger

    m15["Strategy"] = "SMC Market Structure"
    m15["Signal"] = "NEUTRAL"
    m15["Direction"] = "NEUTRAL"
    m15["Reason"] = "No valid SMC confluence"
    m15["Entry"] = m15["SL"] = m15["TP"] = np.nan

    m15.loc[buy, "Signal"], m15.loc[buy, "Direction"], m15.loc[buy, "Reason"], m15.loc[buy, "Entry"] = "BUY", "BUY", "Bullish structure + trigger", m15["Close"]
    m15.loc[sell, "Signal"], m15.loc[sell, "Direction"], m15.loc[sell, "Reason"], m15.loc[sell, "Entry"] = "SELL", "SELL", "Bearish structure + trigger", m15["Close"]

    m15.loc[buy, "SL"] = np.minimum(m15["Last_Swing_Low"], m15["Close"] - atr_mult * m15["ATR_14"])
    m15.loc[sell, "SL"] = np.maximum(m15["Last_Swing_High"], m15["Close"] + atr_mult * m15["ATR_14"])

    m15.loc[buy, "TP"] = m15["Close"] + (m15["Close"] - m15["SL"]) * rr
    m15.loc[sell, "TP"] = m15["Close"] - (m15["SL"] - m15["Close"]) * rr

    invalid = ((m15["Signal"] == "BUY") & ((m15["SL"] >= m15["Entry"]) | (m15["TP"] <= m15["Entry"]))) | \
              ((m15["Signal"] == "SELL") & ((m15["SL"] <= m15["Entry"]) | (m15["TP"] >= m15["Entry"])))
    m15.loc[invalid, ["Signal", "Direction", "Reason", "Entry", "SL", "TP"]] = ["NEUTRAL", "NEUTRAL", "Invalid SL/TP", np.nan, np.nan, np.nan]

    m15 = add_cameroon_time(m15, start_hour, end_hour)
    if enforce_window:
        outside = ~m15["Trading_Window"]
        m15.loc[outside & m15["Signal"].isin(["BUY", "SELL"]), ["Signal", "Direction", "Reason"]] = ["NEUTRAL", "NEUTRAL", "Outside watch time"]
        m15.loc[outside, ["Entry", "SL", "TP"]] = np.nan

    return daily, h1, m15

# =====================================================
# CHARTS & UI HELPERS
# =====================================================

def candle_chart(df, market, title):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["Date"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"))
    if "Signal" in df.columns:
        buys = df[df["Signal"] == "BUY"]
        sells = df[df["Signal"] == "SELL"]
        if not buys.empty: fig.add_trace(go.Scatter(x=buys["Date"], y=buys["Entry"], mode="markers", name="BUY", marker=dict(size=12, symbol="triangle-up", color="green")))
        if not sells.empty: fig.add_trace(go.Scatter(x=sells["Date"], y=sells["Entry"], mode="markers", name="SELL", marker=dict(size=12, symbol="triangle-down", color="red")))
    fig.update_layout(title=title, height=500, xaxis_rangeslider_visible=False)
    return fig

def color_rows(df):
    def apply(row):
        sig = str(row.get("Signal", row.get("Direction", ""))).upper()
        if "BUY" in sig: return [f"background-color: {BUY_BG}; color: #065f46"] * len(row)
        if "SELL" in sig: return [f"background-color: {SELL_BG}; color: #991b1b"] * len(row)
        return [f"background-color: {NEUTRAL_BG}; color: #9a3412"] * len(row)
    return df.style.apply(apply, axis=1)

# =====================================================
# APP START & SIDEBAR
# =====================================================

st.markdown('<div class="main-title">⚡ SMC Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">EURUSD & XAUUSD</div>', unsafe_allow_html=True)

if "page" not in st.session_state: st.session_state["page"] = "Dashboard"
if "last_alert" not in st.session_state: st.session_state["last_alert"] = {}

with st.sidebar:
    st.header("Main Controls")
    market = st.selectbox("Active Analysis Market", list(PAIRS.keys()), index=0)
    daily_start = st.date_input("Daily data start", value=pd.to_datetime("2020-01-01"))

    st.divider()
    st.subheader("Risk Management")
    account_balance = st.number_input("Account balance", min_value=10.0, value=10000.0, step=100.0)
    risk_percent = st.selectbox("Risk % per trade", [0.25, 0.5, 1.0, 1.5, 2.0], index=1)
    rr_label = st.selectbox("Risk Reward", list(RR_OPTIONS.keys()), index=4)
    rr_ratio = RR_OPTIONS[rr_label]

    st.divider()
    st.subheader("Strategy Settings")
    atr_mult = st.selectbox("ATR safety buffer", [0.5, 1.0, 1.5, 2.0], index=2)
    swing_len = st.selectbox("SMC swing sensitivity", [2, 3, 4, 5], index=0)
    strict_mode = st.checkbox("SMC strict Daily + 1H alignment", value=False)

    st.divider()
    st.subheader("Cameroon Watch Time")
    enforce_session = st.checkbox("Only allow signals during watch time", value=True)
    session_start = st.selectbox("Start", list(range(0, 24)), index=6, format_func=lambda x: f"{x:02d}:00 Cameroon")
    session_end = st.selectbox("Stop", list(range(1, 25)), index=21, format_func=lambda x: f"{x if x < 24 else 0:02d}:00 Cameroon")

    if st.button("Refresh Market Data"):
        st.cache_data.clear()
        st.rerun()

pages = ["Dashboard", "Analysis"]
pcols = st.columns(len(pages))
for i, p in enumerate(pages):
    if pcols[i].button("✅ " + p if st.session_state["page"] == p else p, use_container_width=True):
        st.session_state["page"] = p
        st.rerun()

st.divider()

# Core Data Load for Analysis Tab
analysis_error = None
if st.session_state["page"] == "Analysis":
    try:
        d_raw, h_raw, m_raw = load_market_data(market, str(daily_start))
        if d_raw.empty or h_raw.empty or m_raw.empty:
            analysis_error = "Not enough data. Try another market."
        else:
            daily, h1, m15 = build_smc_strategy(d_raw, h_raw, m_raw, rr_ratio, atr_mult, swing_len, strict_mode, session_start, session_end, enforce_session)
            valid = m15.dropna(subset=["Close"])
            latest = valid.iloc[-1] if not valid.empty else None
    except Exception as e:
        analysis_error = str(e)


# =====================================================
# DASHBOARD PAGE (FAST SCANNER)
# =====================================================

if st.session_state["page"] == "Dashboard":
    
    cols = st.columns(2)
    table = []
    recent_start = str(date.today() - pd.Timedelta(days=14))

    def fetch_pair_data(pair_name):
        try:
            d, h, m = load_market_data(pair_name, recent_start)
            return pair_name, d, h, m
        except: return pair_name, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    with st.spinner("Scanning markets instantly..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            for pair_name in PAIRS.keys():
                future = executor.submit(fetch_pair_data, pair_name)
                # Attach the Streamlit context to the background thread
                add_script_run_ctx(future) 
                futures.append(future)
            
            fetched_data = [f.result() for f in futures]

    for i, (name, scan_d, scan_h, scan_m) in enumerate(fetched_data):
        config = PAIRS[name]
        if scan_d.empty or scan_h.empty or scan_m.empty: continue

        try:
            _, _, scan_res = build_smc_strategy(scan_d, scan_h, scan_m, rr_ratio, atr_mult, swing_len, strict_mode, session_start, session_end, enforce_session)
            scan_valid = scan_res.dropna(subset=["Close"])
            if scan_valid.empty: continue
            
            row = scan_valid.iloc[-1]
            sig = row.get("Signal", "NEUTRAL")
            price = row["Close"]
            
            with cols[i]:
                st.metric(name, f"{price:.{config['decimals']}f}")
                if sig == "BUY": st.success("BUY")
                elif sig == "SELL": st.error("SELL")
                else: st.warning("NEUTRAL")

            prev = st.session_state["last_alert"].get(name)
            if sig in ["BUY", "SELL"] and sig != prev:
                send_alert(f"🔥 SMC Alert\nSymbol: {name}\nSignal: {sig}\nPrice: {price:.{config['decimals']}f}")
                st.session_state["last_alert"][name] = sig

            table.append({"Symbol": name, "Price": round(price, config["decimals"]), "Signal": sig, "Reason": row.get("Reason", "")})
        except: pass

    st.subheader("Market Overview")
    st.dataframe(color_rows(pd.DataFrame(table)), use_container_width=True)

# =====================================================
# ANALYSIS PAGE
# =====================================================

elif st.session_state["page"] == "Analysis":
    st.subheader(f"SMC Analysis - {market}")

    if analysis_error: st.error(analysis_error)
    else:
        if latest is not None:
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Signal", latest.get("Signal", "NEUTRAL"))
            s2.metric("Direction", latest.get("Direction", "NEUTRAL"))
            s3.metric("Entry", fmt_price(market, latest.get("Entry", np.nan)))
            s4.metric("SL", fmt_price(market, latest.get("SL", np.nan)))
            s5.metric("TP", fmt_price(market, latest.get("TP", np.nan)))

        st.plotly_chart(candle_chart(m15.tail(150), market, f"{market} 15m Chart"), use_container_width=True)

        setups = m15[m15["Signal"].isin(["BUY", "SELL"])].dropna(subset=["Entry", "SL", "TP"]).tail(20)
        st.subheader("Latest Valid Setups")
        if setups.empty: st.warning("No valid setups found.")
        else:
            cols = ["Date", "Signal", "Daily_Bias", "H1_Structure", "Entry", "SL", "TP", "Reason"]
            st.dataframe(color_rows(setups[cols]), use_container_width=True)
