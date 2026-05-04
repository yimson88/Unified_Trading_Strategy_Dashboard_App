
# FULL MT5 + STREAMLIT TRADING DASHBOARD (SMC + FX + JOURNAL + ALERTS)

import streamlit as st
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import requests
import os

# =========================
# CONFIG
# =========================

st.set_page_config(layout="wide")

# Auto refresh
st_autorefresh(interval=60000, key="refresh")

BOT_TOKEN = "8775932132:AAFQUiigqXKQuNHbEF9w86pyj-SJK2-f5Rs"
CHAT_ID = "8512166732"

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
TIMEFRAME = mt5.TIMEFRAME_M15

DATA_FILE = "journal.csv"

# =========================
# MT5 CONNECT
# =========================

def connect():
    if not mt5.initialize():
        st.error("MT5 not connected")
        return False
    return True

# =========================
# TELEGRAM
# =========================

def send_alert(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# =========================
# DATA
# =========================

def get_data(symbol, bars=300):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, bars)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df

# =========================
# INDICATORS
# =========================

def add_indicators(df):
    df["EMA9"] = df["close"].ewm(span=9).mean()
    df["EMA21"] = df["close"].ewm(span=21).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))

    return df

# =========================
# FX STRATEGY
# =========================

def fx_strategy(df):
    last = df.iloc[-1]
    if last["EMA9"] > last["EMA21"] and last["RSI"] > 50:
        return "BUY"
    elif last["EMA9"] < last["EMA21"] and last["RSI"] < 50:
        return "SELL"
    return "NEUTRAL"

# =========================
# SIMPLE SMC (basic version)
# =========================

def smc_strategy(df):
    high = df["high"]
    low = df["low"]

    if high.iloc[-1] > high.iloc[-5:-1].max():
        return "BUY"
    elif low.iloc[-1] < low.iloc[-5:-1].min():
        return "SELL"
    return "NEUTRAL"

# =========================
# JOURNAL
# =========================

def load_journal():
    if os.path.exists(DATA_FILE):
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Symbol","Signal","Price","Time"])

def save_journal(df):
    df.to_csv(DATA_FILE, index=False)

journal = load_journal()

# =========================
# SESSION STATE
# =========================

if "last_signal" not in st.session_state:
    st.session_state["last_signal"] = {}

if "strategy" not in st.session_state:
    st.session_state["strategy"] = "FX"

# =========================
# UI
# =========================

st.title("🚀 LIVE TRADING DASHBOARD (MT5)")

if not connect():
    st.stop()

# Strategy toggle
col1, col2 = st.columns(2)

if col1.button("FX Strategy"):
    st.session_state["strategy"] = "FX"

if col2.button("SMC Strategy"):
    st.session_state["strategy"] = "SMC"

st.write("Active Strategy:", st.session_state["strategy"])

# =========================
# MAIN LOOP
# =========================

cols = st.columns(len(SYMBOLS))

table = []

for i, symbol in enumerate(SYMBOLS):

    df = get_data(symbol)
    df = add_indicators(df)

    if st.session_state["strategy"] == "FX":
        signal = fx_strategy(df)
    else:
        signal = smc_strategy(df)

    price = df.iloc[-1]["close"]

    with cols[i]:
        st.metric(symbol, round(price, 5))
        st.write(signal)

    # Alerts
    prev = st.session_state["last_signal"].get(symbol)

    if signal in ["BUY","SELL"] and signal != prev:
        msg = f"{symbol} {signal} @ {price}"
        send_alert(msg)
        st.session_state["last_signal"][symbol] = signal

        journal = pd.concat([journal, pd.DataFrame([{
            "Symbol": symbol,
            "Signal": signal,
            "Price": price,
            "Time": datetime.now()
        }])])

        save_journal(journal)

    table.append({
        "Symbol": symbol,
        "Price": price,
        "Signal": signal
    })

# =========================
# TABLE
# =========================

st.subheader("Market Overview")
st.dataframe(pd.DataFrame(table), use_container_width=True)

# =========================
# JOURNAL VIEW
# =========================

st.subheader("Trade Journal")

if journal.empty:
    st.info("No trades yet")
else:
    st.dataframe(journal.tail(50), use_container_width=True)

# =========================
# BACKTEST (simple)
# =========================

st.subheader("Quick Backtest")

symbol_bt = st.selectbox("Select Symbol", SYMBOLS)

if st.button("Run Backtest"):
    df = get_data(symbol_bt, 500)
    df = add_indicators(df)

    results = []

    for i in range(20, len(df)):
        slice_df = df.iloc[:i]

        if st.session_state["strategy"] == "FX":
            sig = fx_strategy(slice_df)
        else:
            sig = smc_strategy(slice_df)

        results.append(sig)

    st.write("Signals generated:", len([r for r in results if r!="NEUTRAL"]))

st.warning("MT5 must stay open. This is not a full auto trading bot yet.")
