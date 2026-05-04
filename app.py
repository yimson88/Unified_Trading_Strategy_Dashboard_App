# PRO TRADING DASHBOARD (STABLE YFINANCE VERSION - HARMONIZED UI)

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import requests
import os

# =====================================================
# CONFIG & SETUP
# =====================================================
st.set_page_config(
    page_title="PRO Trading Dashboard",
    page_icon="🔥",
    layout="wide"
)

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="refresh")

BOT_TOKEN = "8775932132:AAFQUiigqXKQuNHbEF9w86pyj-SJK2-f5Rs"
CHAT_ID = "8512166732"

SYMBOLS = {
    "EURUSD": {"ticker": "EURUSD=X", "decimals": 5},
    "GBPUSD": {"ticker": "GBPUSD=X", "decimals": 5},
    "XAUUSD": {"ticker": "GC=F", "decimals": 2},
    "BTCUSD": {"ticker": "BTC-USD", "decimals": 2}
}

DATA_FILE = "pro_journal.csv"

# Colors for UI
BUY_BG = "#dcfce7"
SELL_BG = "#fee2e2"
NEUTRAL_BG = "#ffedd5"

# =====================================================
# CSS STYLING
# =====================================================
st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
.main-title { font-size: 34px; font-weight: 900; color: #0f172a; margin-bottom: 0.2rem; }
.subtitle { color: #64748b; font-size: 15px; margin-bottom: 1rem; }
.card { background: white; border: 1px solid #e5e7eb; border-radius: 20px; padding: 18px; box-shadow: 0 8px 24px rgba(15,23,42,0.06); margin-bottom: 14px; }
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

@st.cache_data(ttl=60)
def get_data(symbol, interval):
    df = yf.download(symbol, period="10d", interval=interval, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Adj Close": "Close"})
    return df.dropna()

def add_indicators(df):
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    return df

def add_structure(df):
    df = df.copy()
    if df.empty or len(df) < 10:
        return df

    df["HH"] = df["High"].rolling(5).max()
    df["LL"] = df["Low"].rolling(5).min()

    close = df["Close"]
    hh_shift = df["HH"].shift(1)
    ll_shift = df["LL"].shift(1)

    df["BOS_Bull"] = (close > hh_shift).fillna(False)
    df["BOS_Bear"] = (close < ll_shift).fillna(False)

    df["CHOCH_Bull"] = df["BOS_Bull"] & (~df["BOS_Bull"].shift(1).fillna(False))
    df["CHOCH_Bear"] = df["BOS_Bear"] & (~df["BOS_Bear"].shift(1).fillna(False))

    df["Liquidity_Sweep_H"] = ((df["High"] > hh_shift) & (close < hh_shift)).fillna(False)
    df["Liquidity_Sweep_L"] = ((df["Low"] < ll_shift) & (close > ll_shift)).fillna(False)

    return df

def analyze(symbol):
    d1 = get_data(symbol, "1d")
    h1 = get_data(symbol, "1h")
    m15 = get_data(symbol, "15m")

    if d1.empty or h1.empty or m15.empty:
        return pd.DataFrame(), "NO DATA", 0

    d1 = add_structure(add_indicators(d1))
    h1 = add_structure(add_indicators(h1))
    m15 = add_structure(add_indicators(m15))

    latest_d1 = d1.iloc[-1]
    latest_h1 = h1.iloc[-1]
    latest_m15 = m15.iloc[-1]

    score = 0
    if latest_d1["Close"] > latest_d1["EMA50"]: score += 1
    else: score -= 1

    if latest_h1["BOS_Bull"]: score += 1
    if latest_h1["BOS_Bear"]: score -= 1

    if latest_m15["CHOCH_Bull"] or latest_m15["Liquidity_Sweep_L"]: score += 2
    if latest_m15["CHOCH_Bear"] or latest_m15["Liquidity_Sweep_H"]: score -= 2

    if score >= 2: signal = "BUY"
    elif score <= -2: signal = "SELL"
    else: signal = "NEUTRAL"

    confidence = min(abs(score) / 4 * 100, 100)
    return m15, signal, confidence

def plot_chart(df, symbol_name):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA20"], name="EMA20", line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], name="EMA50", line=dict(color='orange')))
    fig.update_layout(title=f"{symbol_name} 15m Chart", height=500, xaxis_rangeslider_visible=False)
    return fig

def load_journal():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Symbol", "Signal", "Confidence", "Price", "Time", "Result", "Notes"])

def save_journal(df):
    df.to_csv(DATA_FILE, index=False)

def color_rows(df):
    def apply(row):
        sig = str(row.get("Signal", "")).upper()
        if "BUY" in sig: return [f"background-color: {BUY_BG}; color: #065f46"] * len(row)
        if "SELL" in sig: return [f"background-color: {SELL_BG}; color: #991b1b"] * len(row)
        return [f"background-color: {NEUTRAL_BG}; color: #9a3412"] * len(row)
    return df.style.apply(apply, axis=1)

journal = load_journal()

if "last_signal" not in st.session_state:
    st.session_state["last_signal"] = {}
if "page" not in st.session_state:
    st.session_state["page"] = "Dashboard"

# =====================================================
# SIDEBAR & NAVIGATION
# =====================================================
with st.sidebar:
    st.header("Navigation")
    pages = ["Dashboard", "Analysis", "Journal"]
    for p in pages:
        if st.button("✅ " + p if st.session_state["page"] == p else p, use_container_width=True):
            st.session_state["page"] = p
            st.rerun()
            
    st.divider()
    st.header("Settings")
    market = st.selectbox("Market Analysis", list(SYMBOLS.keys()), index=0)
    if st.button("Force Data Refresh"):
        st.cache_data.clear()
        st.rerun()

st.markdown('<div class="main-title">🔥 PRO TRADING DASHBOARD</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">SMC + MTF Signals mapped directly to your Telegram Alerts.</div>', unsafe_allow_html=True)
st.divider()

# =====================================================
# DASHBOARD PAGE
# =====================================================
if st.session_state["page"] == "Dashboard":
    cols = st.columns(len(SYMBOLS))
    table = []

    for i, (name, config) in enumerate(SYMBOLS.items()):
        ticker = config["ticker"]
        df, signal, confidence = analyze(ticker)

        if df.empty:
            with cols[i]:
                st.metric(name, "No Data")
            continue

        price = df.iloc[-1]["Close"]
        
        with cols[i]:
            st.metric(name, f"{price:.{config['decimals']}f}")
            if signal == "BUY":
                st.success(f"{signal} ({confidence:.0f}%)")
            elif signal == "SELL":
                st.error(f"{signal} ({confidence:.0f}%)")
            else:
                st.warning(f"{signal} ({confidence:.0f}%)")
            st.progress(int(confidence) / 100)

        # Telegram Logic
        prev = st.session_state["last_signal"].get(name)
        if signal in ["BUY", "SELL"] and signal != prev:
            msg = f"🔥 {name} {signal} ({confidence:.0f}%) @ {price:.{config['decimals']}f}"
            send_alert(msg)
            st.session_state["last_signal"][name] = signal

            journal = pd.concat([journal, pd.DataFrame([{
                "Symbol": name,
                "Signal": signal,
                "Confidence": confidence,
                "Price": price,
                "Time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Result": "Open",
                "Notes": ""
            }])], ignore_index=True)
            save_journal(journal)

        table.append({
            "Symbol": name,
            "Price": round(price, config["decimals"]),
            "Signal": signal,
            "Confidence %": round(confidence, 1)
        })

    st.subheader("Live Market Overview")
    st.dataframe(color_rows(pd.DataFrame(table)), use_container_width=True)
    st.caption("Uses Yahoo Finance data. Auto-refreshes every 60 seconds.")

# =====================================================
# ANALYSIS PAGE
# =====================================================
elif st.session_state["page"] == "Analysis":
    st.subheader(f"Deep Analysis - {market}")
    
    df_chart, current_signal, conf = analyze(SYMBOLS[market]["ticker"])
    
    if not df_chart.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Current Signal", current_signal)
        c2.metric("Confidence", f"{conf}%")
        c3.metric("Latest Close", f"{df_chart.iloc[-1]['Close']:.{SYMBOLS[market]['decimals']}f}")
        
        st.plotly_chart(plot_chart(df_chart.tail(200), market), use_container_width=True)
        
        # Show SMC specific tails
        st.subheader("Raw MTF Indicators (Last 10 Candles)")
        show_cols = ["Close", "EMA20", "EMA50", "BOS_Bull", "BOS_Bear", "CHOCH_Bull", "CHOCH_Bear"]
        st.dataframe(df_chart[show_cols].tail(10), use_container_width=True)
    else:
        st.error("Not enough data to run analysis.")

# =====================================================
# JOURNAL PAGE
# =====================================================
elif st.session_state["page"] == "Journal":
    st.subheader("Automated Trade Journal")

    if journal.empty:
        st.info("No trades recorded yet. Alerts will automatically log here.")
    else:
        st.dataframe(color_rows(journal.sort_values(by="Time", ascending=False)), use_container_width=True)
        csv = journal.to_csv(index=False).encode('utf-8')
        st.download_button("Download Journal CSV", data=csv, file_name="pro_journal.csv", mime="text/csv")