


# PRO TRADING DASHBOARD (STABLE YFINANCE VERSION - MATCHED UI + ADVANCED FEATURES)

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import requests
import os

st.set_page_config(layout="wide")
st_autorefresh(interval=60000, key="refresh")



# =========================
# CONFIG
# =========================
BOT_TOKEN = "8775932132:AAFQUiigqXKQuNHbEF9w86pyj-SJK2-f5Rs"
CHAT_ID = "8512166732"

SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD"
}

DATA_FILE = "journal.csv"

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
    df = df.dropna()

    return df

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

    if latest_d1["Close"] > latest_d1["EMA50"]:
        score += 1
    else:
        score -= 1

    if latest_h1["BOS_Bull"]:
        score += 1
    if latest_h1["BOS_Bear"]:
        score -= 1

    if latest_m15["CHOCH_Bull"] or latest_m15["Liquidity_Sweep_L"]:
        score += 2
    if latest_m15["CHOCH_Bear"] or latest_m15["Liquidity_Sweep_H"]:
        score -= 2

    if score >= 2:
        signal = "BUY"
    elif score <= -2:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    confidence = min(abs(score) / 4 * 100, 100)

    return m15, signal, confidence

def plot_chart(df):
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"]
    ))

    fig.add_trace(go.Scatter(x=df.index, y=df["EMA20"], name="EMA20"))
    fig.add_trace(go.Scatter(x=df.index, y=df["EMA50"], name="EMA50"))

    fig.update_layout(height=500)
    return fig

def load_journal():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Symbol","Signal","Confidence","Price","Time"])

def save_journal(df):
    df.to_csv(DATA_FILE, index=False)

journal = load_journal()

if "last_signal" not in st.session_state:
    st.session_state["last_signal"] = {}

st.title("🔥 PRO TRADING DASHBOARD (SMC + MTF)")

cols = st.columns(len(SYMBOLS))
table = []

for i, (name, ticker) in enumerate(SYMBOLS.items()):

    df, signal, confidence = analyze(ticker)

    if df.empty:
        continue

    price = df.iloc[-1]["Close"]

    with cols[i]:
        st.metric(name, round(price, 5))
        st.write(signal)
        st.progress(int(confidence))

    prev = st.session_state["last_signal"].get(name)

    if signal in ["BUY","SELL"] and signal != prev:
        msg = f"{name} {signal} ({confidence:.0f}%) @ {price}"
        send_alert(msg)
        st.session_state["last_signal"][name] = signal

        journal = pd.concat([journal, pd.DataFrame([{
            "Symbol": name,
            "Signal": signal,
            "Confidence": confidence,
            "Price": price,
            "Time": datetime.now()
        }])])

        save_journal(journal)

    table.append({
        "Symbol": name,
        "Price": price,
        "Signal": signal,
        "Confidence %": round(confidence,1)
    })

st.subheader("Market Overview")
st.dataframe(pd.DataFrame(table), use_container_width=True)

st.subheader("Chart")
symbol_choice = st.selectbox("Select Symbol", list(SYMBOLS.keys()))
df_chart, _, _ = analyze(SYMBOLS[symbol_choice])

if not df_chart.empty:
    st.plotly_chart(plot_chart(df_chart.tail(200)), use_container_width=True)

st.subheader("Trade Journal")

if journal.empty:
    st.info("No trades yet")
else:
    st.dataframe(journal.tail(50), use_container_width=True)

st.warning("Uses Yahoo Finance data (may be delayed).")