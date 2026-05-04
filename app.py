# UNIFIED PRO TRADING DASHBOARD (ALL FEATURES + TELEGRAM ALERTS)
import concurrent.futures
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from pathlib import Path
from datetime import date, datetime
import requests
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Unified PRO Trading Dashboard",
    page_icon="📊",
    layout="wide"
)

# Auto-refresh the dashboard every 60 seconds
st_autorefresh(interval=60000, key="refresh")

# =====================================================
# CONFIG & TELEGRAM
# =====================================================

BOT_TOKEN = "8775932132:AAFQUiigqXKQuNHbEF9w86pyj-SJK2-f5Rs"
CHAT_ID = "8512166732"

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
JOURNAL_FILE = DATA_DIR / "unified_trading_journal.csv"

PAIRS = {
    "EURUSD": {"ticker": "EURUSD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 1.10000},
    "GBPUSD": {"ticker": "GBPUSD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 1.27000},
    "AUDUSD": {"ticker": "AUDUSD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 0.65000},
    # "NZDUSD": {"ticker": "NZDUSD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 0.60000},
    "USDJPY": {"ticker": "JPY=X", "pip": 0.01, "contract": 100000, "decimals": 3, "default": 150.000},
    # "USDCAD": {"ticker": "CAD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 1.35000},
    # "USDCHF": {"ticker": "CHF=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 0.90000},
    # "EURJPY": {"ticker": "EURJPY=X", "pip": 0.01, "contract": 100000, "decimals": 3, "default": 165.000},
    # "GBPJPY": {"ticker": "GBPJPY=X", "pip": 0.01, "contract": 100000, "decimals": 3, "default": 190.000},
    # "EURAUD": {"ticker": "EURAUD=X", "pip": 0.0001, "contract": 100000, "decimals": 5, "default": 1.65000},
    "XAUUSD": {"ticker": "GC=F", "pip": 0.01, "contract": 100, "decimals": 2, "default": 2350.00},
    "BTCUSD": {"ticker": "BTC-USD", "pip": 1.0, "contract": 1, "decimals": 2, "default": 78000.00},
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
WIN_BG, LOSS_BG = "#bbf7d0", "#fecaca"
TIME_POS_BG, TIME_NEG_BG = "#dcfce7", "#fee2e2"

# =====================================================
# CSS
# =====================================================

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
.main-title { font-size: 34px; font-weight: 900; color: #0f172a; margin-bottom: 0.2rem; }
.subtitle { color: #64748b; font-size: 15px; margin-bottom: 1rem; }
.card { background: white; border: 1px solid #e5e7eb; border-radius: 20px; padding: 18px; box-shadow: 0 8px 24px rgba(15,23,42,0.06); margin-bottom: 14px; }
.strategy-active { background: #0f172a; color: white; padding: 12px; border-radius: 14px; text-align: center; font-weight: 800; }
.strategy-inactive { background: #f1f5f9; color: #0f172a; padding: 12px; border-radius: 14px; text-align: center; font-weight: 700; }
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
    if market == "BTCUSD": return 1.0
    if market == "XAUUSD" or "JPY" in market: return 0.01
    return 0.0001

@st.cache_data(ttl=90)
def get_live_price(market):
    fallback = PAIRS[market]["default"]
    ticker = PAIRS[market]["ticker"]
    try:
        tk = yf.Ticker(ticker)
        fast = getattr(tk, "fast_info", None)
        if fast is not None:
            last = fast.get("last_price", None)
            if last is not None and not pd.isna(last) and float(last) > 0:
                return float(last), "Yahoo fast_info"
    except: pass
    try:
        raw = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=False)
        if raw is not None and not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
            close = pd.to_numeric(raw["Close"], errors="coerce").dropna()
            if not close.empty:
                return float(close.iloc[-1]), "Yahoo latest close"
    except: pass
    return fallback, "Fallback default"

def clean_data(raw):
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.reset_index()
    if "Datetime" in df.columns: df.rename(columns={"Datetime": "Date"}, inplace=True)
    if "Date" not in df.columns: df.rename(columns={df.columns[0]: "Date"}, inplace=True)
    if "Volume" not in df.columns: df["Volume"] = 0
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert(None)
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    df = df[(df[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    return df.sort_values("Date").reset_index(drop=True)

@st.cache_data(ttl=600)
def load_market_data(market, daily_start):
    ticker = PAIRS[market]["ticker"]
    daily_raw = yf.download(ticker, start=daily_start, interval="1d", progress=False, auto_adjust=False)
    h1_raw = yf.download(ticker, period="730d", interval="1h", progress=False, auto_adjust=False)
    m15_raw = yf.download(ticker, period="60d", interval="15m", progress=False, auto_adjust=False)
    return clean_data(daily_raw), clean_data(h1_raw), clean_data(m15_raw)

def add_cameroon_time(df, start_hour, end_hour):
    df = df.copy()
    local = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert("Africa/Douala")
    df["Cameroon_Time"] = local.dt.strftime("%Y-%m-%d %H:%M")
    hour = local.dt.hour + local.dt.minute / 60
    if start_hour < end_hour:
        df["Trading_Window"] = (hour >= start_hour) & (hour < end_hour)
    else:
        df["Trading_Window"] = (hour >= start_hour) | (hour < end_hour)
    return df

def load_journal():
    if JOURNAL_FILE.exists():
        df = pd.read_csv(JOURNAL_FILE)
        for c in JOURNAL_COLUMNS:
            if c not in df.columns: df[c] = np.nan
        return df[JOURNAL_COLUMNS]
    return pd.DataFrame(columns=JOURNAL_COLUMNS)

def save_journal(df):
    df = df.copy()
    for c in JOURNAL_COLUMNS:
        if c not in df.columns: df[c] = np.nan
    df[JOURNAL_COLUMNS].to_csv(JOURNAL_FILE, index=False)

def next_trade_id(df):
    if df.empty: return 1
    return int(pd.to_numeric(df["Trade_ID"], errors="coerce").max()) + 1

# =====================================================
# INDICATORS
# =====================================================

def add_rsi(df, period=14):
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    df[f"RSI_{period}"] = 100 - (100 / (1 + rs))
    return df

def add_macd(df):
    df = df.copy()
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    return df

def add_atr(df, period=14):
    df = df.copy()
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df[f"ATR_{period}"] = tr.rolling(period).mean()
    return df

def add_ema(df):
    df = df.copy()
    for s in [9, 20, 21, 50, 200]:
        df[f"EMA_{s}"] = df["Close"].ewm(span=s, adjust=False).mean()
    return df

def add_sma(df):
    df = df.copy()
    for s in [20, 50, 200]:
        df[f"SMA_{s}"] = df["Close"].rolling(s).mean()
    return df

# =====================================================
# RISK CALCULATIONS
# =====================================================

def rr_value(label): return RR_OPTIONS[label]

def stop_presets(market):
    if market == "BTCUSD": return {"Tight $500": 500.0, "Normal $1000": 1000.0, "Wide $1500": 1500.0, "Very Wide $2000": 2000.0}
    if market == "XAUUSD": return {"Tight $5": 5.0, "Normal $10": 10.0, "Wide $15": 15.0, "Very Wide $20": 20.0}
    if "JPY" in market: return {"Tight 15 pips": 0.15, "Normal 25 pips": 0.25, "Wide 40 pips": 0.40, "Very Wide 60 pips": 0.60}
    return {"Tight 15 pips": 0.0015, "Normal 25 pips": 0.0025, "Wide 40 pips": 0.0040, "Very Wide 60 pips": 0.0060}

def sl_tp_from_distance(direction, entry, stop_distance, rr):
    if direction == "BUY": return entry - stop_distance, entry + stop_distance * rr
    return entry + stop_distance, entry - stop_distance * rr

def pip_value_standard_lot(market, entry, usd_jpy, aud_usd):
    pip = PAIRS[market]["pip"]
    contract = PAIRS[market]["contract"]
    if market in ["XAUUSD", "BTCUSD"]: return None
    if market.endswith("USD"): return contract * pip
    if market.startswith("USD"): return (contract * pip) / entry
    if "JPY" in market: return (contract * pip) / usd_jpy
    if market == "EURAUD": return (contract * pip) * aud_usd
    return contract * pip

def calc_position(market, direction, entry, sl, tp, balance, risk_percent, usd_jpy, aud_usd):
    risk_amount = balance * risk_percent / 100
    stop_distance = abs(entry - sl)
    reward_distance = abs(tp - entry)
    pip = PAIRS[market]["pip"]
    contract = PAIRS[market]["contract"]

    if stop_distance <= 0: raise ValueError("Stop-loss distance must be greater than zero.")
    if direction == "BUY" and not (sl < entry < tp): raise ValueError("BUY trade needs SL below entry and TP above entry.")
    if direction == "SELL" and not (tp < entry < sl): raise ValueError("SELL trade needs TP below entry and SL above entry.")

    stop_pips = stop_distance / pip
    planned_rr = reward_distance / stop_distance

    if market == "XAUUSD":
        position_size = risk_amount / stop_distance
        lot_size = position_size / contract
    elif market == "BTCUSD":
        position_size = risk_amount / stop_distance
        lot_size = position_size
    else:
        pv = pip_value_standard_lot(market, entry, usd_jpy, aud_usd)
        lot_size = risk_amount / (stop_pips * pv)
        position_size = lot_size * contract

    return {
        "risk_amount": risk_amount,
        "stop_distance": stop_distance,
        "stop_pips": stop_pips,
        "lot_size": lot_size,
        "position_size": position_size,
        "planned_rr": planned_rr,
    }

def calc_pnl(direction, entry, exit_price, position_size, risk_amount):
    if exit_price is None or pd.isna(exit_price) or exit_price == 0:
        return np.nan, np.nan
    move = exit_price - entry if direction == "BUY" else entry - exit_price
    pnl = move * position_size
    r = pnl / risk_amount if risk_amount > 0 else np.nan
    return pnl, r

# =====================================================
# STRATEGIES
# =====================================================

def build_fx15_strategy(daily, h1, m15, rr, atr_mult, start_hour, end_hour, enforce_window):
    daily = add_sma(add_rsi(add_macd(daily)))
    daily["Daily_Bias"] = "Neutral"
    daily.loc[(daily["Close"] > daily["SMA_200"]) & (daily["SMA_20"] > daily["SMA_50"]) & (daily["RSI_14"] > 50) & (daily["MACD"] > daily["MACD_Signal"]), "Daily_Bias"] = "Bullish"
    daily.loc[(daily["Close"] < daily["SMA_200"]) & (daily["SMA_20"] < daily["SMA_50"]) & (daily["RSI_14"] < 50) & (daily["MACD"] < daily["MACD_Signal"]), "Daily_Bias"] = "Bearish"
    daily["Daily_Bias"] = daily["Daily_Bias"].shift(1).fillna("Neutral")

    h1 = add_ema(add_rsi(add_macd(h1)))
    h1["H1_Structure"] = "Neutral"
    h1.loc[(h1["EMA_9"] > h1["EMA_21"]) & (h1["EMA_21"] > h1["EMA_50"]) & (h1["RSI_14"] > 50) & (h1["MACD"] > h1["MACD_Signal"]), "H1_Structure"] = "Bullish"
    h1.loc[(h1["EMA_9"] < h1["EMA_21"]) & (h1["EMA_21"] < h1["EMA_50"]) & (h1["RSI_14"] < 50) & (h1["MACD"] < h1["MACD_Signal"]), "H1_Structure"] = "Bearish"
    h1["H1_Structure"] = h1["H1_Structure"].shift(1).fillna("Neutral")

    m15 = add_ema(add_rsi(add_macd(add_atr(m15))))
    daily_state = daily[["Date", "Daily_Bias"]].dropna().sort_values("Date")
    h1_state = h1[["Date", "H1_Structure"]].dropna().sort_values("Date")
    m15 = m15.sort_values("Date").reset_index(drop=True)

    if not daily_state.empty: m15 = pd.merge_asof(m15, daily_state, on="Date", direction="backward")
    else: m15["Daily_Bias"] = "Neutral"

    if not h1_state.empty: m15 = pd.merge_asof(m15, h1_state, on="Date", direction="backward")
    else: m15["H1_Structure"] = "Neutral"

    buy = (m15["Daily_Bias"] == "Bullish") & (m15["H1_Structure"] == "Bullish") & (m15["EMA_9"] > m15["EMA_21"]) & (m15["RSI_14"] > 50) & (m15["MACD"] > m15["MACD_Signal"])
    sell = (m15["Daily_Bias"] == "Bearish") & (m15["H1_Structure"] == "Bearish") & (m15["EMA_9"] < m15["EMA_21"]) & (m15["RSI_14"] < 50) & (m15["MACD"] < m15["MACD_Signal"])

    m15["Strategy"] = "FX 15m Momentum"
    m15["Signal"] = "NEUTRAL"
    m15["Direction"] = "NEUTRAL"
    m15["Reason"] = "No aligned 15m momentum setup"
    m15["Entry"] = m15["SL"] = m15["TP"] = np.nan

    risk_dist = atr_mult * m15["ATR_14"]

    m15.loc[buy, "Signal"] = "BUY"
    m15.loc[buy, "Direction"] = "BUY"
    m15.loc[buy, "Reason"] = "Daily bullish + 1H bullish + 15m momentum confirmation"
    m15.loc[buy, "Entry"] = m15["Close"]
    m15.loc[buy, "SL"] = m15["Close"] - risk_dist
    m15.loc[buy, "TP"] = m15["Close"] + risk_dist * rr

    m15.loc[sell, "Signal"] = "SELL"
    m15.loc[sell, "Direction"] = "SELL"
    m15.loc[sell, "Reason"] = "Daily bearish + 1H bearish + 15m momentum confirmation"
    m15.loc[sell, "Entry"] = m15["Close"]
    m15.loc[sell, "SL"] = m15["Close"] + risk_dist
    m15.loc[sell, "TP"] = m15["Close"] - risk_dist * rr

    m15 = add_cameroon_time(m15, start_hour, end_hour)

    if enforce_window:
        outside = ~m15["Trading_Window"]
        m15.loc[outside & m15["Signal"].isin(["BUY", "SELL"]), ["Signal", "Direction", "Reason"]] = ["NEUTRAL", "NEUTRAL", "Outside Cameroon watch time"]
        m15.loc[outside, ["Entry", "SL", "TP"]] = np.nan

    return daily, h1, m15

def add_swings(df, n):
    df = df.copy()
    df["Swing_High"] = np.nan
    df["Swing_Low"] = np.nan
    if len(df) < n * 2 + 1:
        df["Last_Swing_High"] = df["Last_Swing_Low"] = np.nan
        return df

    for i in range(n, len(df) - n):
        if df["High"].iloc[i] == df["High"].iloc[i-n:i+n+1].max():
            df.loc[df.index[i], "Swing_High"] = df["High"].iloc[i]
        if df["Low"].iloc[i] == df["Low"].iloc[i-n:i+n+1].min():
            df.loc[df.index[i], "Swing_Low"] = df["Low"].iloc[i]

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

    m15.loc[buy, "Signal"] = "BUY"
    m15.loc[buy, "Direction"] = "BUY"
    m15.loc[buy, "Reason"] = "Bullish structure + liquidity/CHOCH/BOS trigger"
    m15.loc[buy, "Entry"] = m15["Close"]
    
    m15.loc[sell, "Signal"] = "SELL"
    m15.loc[sell, "Direction"] = "SELL"
    m15.loc[sell, "Reason"] = "Bearish structure + liquidity/CHOCH/BOS trigger"
    m15.loc[sell, "Entry"] = m15["Close"]

    buy_sl = np.minimum(m15["Last_Swing_Low"], m15["Close"] - atr_mult * m15["ATR_14"])
    sell_sl = np.maximum(m15["Last_Swing_High"], m15["Close"] + atr_mult * m15["ATR_14"])

    m15.loc[buy, "SL"] = buy_sl
    m15.loc[sell, "SL"] = sell_sl

    buy_risk = m15["Close"] - m15["SL"]
    sell_risk = m15["SL"] - m15["Close"]

    m15.loc[buy, "TP"] = m15["Close"] + buy_risk * rr
    m15.loc[sell, "TP"] = m15["Close"] - sell_risk * rr

    invalid_buy = (m15["Signal"] == "BUY") & ((m15["SL"] >= m15["Entry"]) | (m15["TP"] <= m15["Entry"]))
    invalid_sell = (m15["Signal"] == "SELL") & ((m15["SL"] <= m15["Entry"]) | (m15["TP"] >= m15["Entry"]))
    invalid = invalid_buy | invalid_sell

    m15.loc[invalid, ["Signal", "Direction", "Reason"]] = ["NEUTRAL", "NEUTRAL", "Invalid SL/TP"]
    m15.loc[invalid, ["Entry", "SL", "TP"]] = np.nan

    m15 = add_cameroon_time(m15, start_hour, end_hour)

    if enforce_window:
        outside = ~m15["Trading_Window"]
        m15.loc[outside & m15["Signal"].isin(["BUY", "SELL"]), ["Signal", "Direction", "Reason"]] = ["NEUTRAL", "NEUTRAL", "Outside Cameroon watch time"]
        m15.loc[outside, ["Entry", "SL", "TP"]] = np.nan

    return daily, h1, m15

# =====================================================
# BACKTESTING
# =====================================================

def backtest_signals(m15, market, balance, risk_percent, max_hold):
    trades = []
    eq = [balance]
    bal = float(balance)
    pip = PAIRS[market]["pip"]
    d = m15.reset_index(drop=True).copy()
    i = 0

    while i < len(d) - 2:
        row = d.iloc[i]
        if row.get("Signal", "NEUTRAL") not in ["BUY", "SELL"]:
            i += 1
            continue

        entry_idx = i + 1
        if entry_idx >= len(d): break

        direction = row["Direction"]
        entry = float(d.iloc[entry_idx]["Open"])
        sl = float(row["SL"])
        tp = float(row["TP"])

        if direction == "BUY" and not (sl < entry < tp):
            i += 1; continue
        if direction == "SELL" and not (tp < entry < sl):
            i += 1; continue

        exit_idx = min(entry_idx + max_hold, len(d) - 1)
        exit_price = None
        exit_reason = "TIME OUT"

        for j in range(entry_idx, min(entry_idx + max_hold + 1, len(d))):
            high = float(d.iloc[j]["High"])
            low = float(d.iloc[j]["Low"])
            if direction == "BUY":
                if low <= sl: exit_price, exit_reason, exit_idx = sl, "LOSS", j; break
                if high >= tp: exit_price, exit_reason, exit_idx = tp, "WIN", j; break
            else:
                if high >= sl: exit_price, exit_reason, exit_idx = sl, "LOSS", j; break
                if low <= tp: exit_price, exit_reason, exit_idx = tp, "WIN", j; break

        if exit_price is None: exit_price = float(d.iloc[exit_idx]["Close"])

        if direction == "BUY": pips, risk_pips = (exit_price - entry) / pip, (entry - sl) / pip
        else: pips, risk_pips = (entry - exit_price) / pip, (sl - entry) / pip

        if risk_pips <= 0:
            i += 1; continue

        r_mult = pips / risk_pips
        pnl = bal * risk_percent / 100 * r_mult
        bal += pnl
        eq.append(bal)

        result = "Win" if pnl > 0 else "Loss" if pnl < 0 else "Breakeven"
        if exit_reason == "TIME OUT": result = "Timeout Positive" if pnl >= 0 else "Timeout Negative"

        trades.append({
            "Signal Date": row["Date"], "Signal Cameroon Time": row.get("Cameroon_Time", "N/A"),
            "Direction": direction, "Entry": round(entry, PAIRS[market]["decimals"]),
            "SL": round(sl, PAIRS[market]["decimals"]), "TP": round(tp, PAIRS[market]["decimals"]),
            "Exit": round(exit_price, PAIRS[market]["decimals"]), "Exit_Reason": exit_reason,
            "Result": result, "Pips": round(pips, 1), "R_Multiple": round(r_mult, 2),
            "PnL": round(pnl, 2), "Balance": round(bal, 2),
        })
        i = exit_idx + 1

    return pd.DataFrame(trades), pd.DataFrame({"Trade": range(len(eq)), "Balance": eq})

# =====================================================
# CHARTS & UI HELPERS
# =====================================================

def candle_chart(df, market, title):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["Date"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"))
    for col in ["EMA_20", "EMA_50", "EMA_200", "SMA_20", "SMA_50", "SMA_200"]:
        if col in df.columns: fig.add_trace(go.Scatter(x=df["Date"], y=df[col], mode="lines", name=col))
    if "Signal" in df.columns:
        buys = df[df["Signal"] == "BUY"]
        sells = df[df["Signal"] == "SELL"]
        if not buys.empty: fig.add_trace(go.Scatter(x=buys["Date"], y=buys["Entry"], mode="markers", name="BUY", marker=dict(size=12, symbol="triangle-up", color="green")))
        if not sells.empty: fig.add_trace(go.Scatter(x=sells["Date"], y=sells["Entry"], mode="markers", name="SELL", marker=dict(size=12, symbol="triangle-down", color="red")))
    fig.update_layout(title=title, height=560, xaxis_rangeslider_visible=False)
    return fig

def equity_chart(eq):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq["Trade"], y=eq["Balance"], mode="lines+markers", name="Equity"))
    fig.update_layout(title="Equity Curve", height=420)
    return fig

def color_rows(df):
    def apply(row):
        sig = str(row.get("Signal", row.get("Direction", ""))).upper()
        res = str(row.get("Result", "")).upper()
        exit_reason = str(row.get("Exit_Reason", row.get("Exit Reason", ""))).upper()
        pnl = pd.to_numeric(row.get("PnL", np.nan), errors="coerce")

        if res == "WIN": return [f"background-color: {WIN_BG}; color: #065f46"] * len(row)
        if res == "LOSS": return [f"background-color: {LOSS_BG}; color: #991b1b"] * len(row)
        if "TIME" in exit_reason or "TIMEOUT" in res:
            if pd.notna(pnl) and pnl >= 0: return [f"background-color: {TIME_POS_BG}; color: #166534"] * len(row)
            if pd.notna(pnl) and pnl < 0: return [f"background-color: {TIME_NEG_BG}; color: #991b1b"] * len(row)
        if "BUY" in sig: return [f"background-color: {BUY_BG}; color: #065f46"] * len(row)
        if "SELL" in sig: return [f"background-color: {SELL_BG}; color: #991b1b"] * len(row)
        if "NEUTRAL" in sig or sig == "": return [f"background-color: {NEUTRAL_BG}; color: #9a3412"] * len(row)
        return [""] * len(row)
    return df.style.apply(apply, axis=1)

def send_to_ticket(strategy, market, row, risk_percent, rr_label):
    st.session_state["ticket"] = {
        "Strategy": strategy, "Market": market, "Direction": row.get("Direction", "BUY"),
        "Signal": row.get("Signal", "NEUTRAL"), "Entry": row.get("Entry", np.nan),
        "SL": row.get("SL", np.nan), "TP": row.get("TP", np.nan),
        "Risk_Percent": risk_percent, "Risk_Reward": rr_label, "Reason": row.get("Reason", ""),
    }
    st.session_state["page"] = "Trade Ticket"
    st.rerun()

# =====================================================
# APP START & SIDEBAR
# =====================================================

st.markdown('<div class="main-title">📊 Unified PRO Strategy Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Complete framework with MTF/SMC Logic, Backtesting, Live Telegram Alerts, and Journaling.</div>', unsafe_allow_html=True)

if "strategy" not in st.session_state: st.session_state["strategy"] = "SMC Market Structure"
if "page" not in st.session_state: st.session_state["page"] = "Dashboard"
if "last_alert" not in st.session_state: st.session_state["last_alert"] = {}

st.subheader("Trading Strategy Toggle")
scol1, scol2, scol3 = st.columns(3)
if scol1.button(("✅ " if st.session_state["strategy"] == "SMC Market Structure" else "") + "SMC Market Structure", use_container_width=True):
    st.session_state["strategy"] = "SMC Market Structure"
    st.rerun()
if scol2.button(("✅ " if st.session_state["strategy"] == "FX 15m Momentum" else "") + "FX 15m Momentum", use_container_width=True):
    st.session_state["strategy"] = "FX 15m Momentum"
    st.rerun()
if scol3.button(("✅ " if st.session_state["strategy"] == "Manual Risk Calculator" else "") + "Manual Risk Calculator", use_container_width=True):
    st.session_state["strategy"] = "Manual Risk Calculator"
    st.session_state["page"] = "Trade Ticket"
    st.rerun()

strategy = st.session_state["strategy"]

with st.sidebar:
    st.header("Main Controls")
    market = st.selectbox("Active Analysis Market", list(PAIRS.keys()), index=0)
    daily_start = st.date_input("Daily data start", value=pd.to_datetime("2020-01-01"))

    st.divider()
    st.subheader("Risk Management")
    account_balance = st.number_input("Account balance", min_value=10.0, value=10000.0, step=100.0)
    risk_percent = st.selectbox("Risk % per trade", [0.25, 0.5, 1.0, 1.5, 2.0], index=2)
    rr_label = st.selectbox("Risk Reward", list(RR_OPTIONS.keys()), index=2)
    rr_ratio = RR_OPTIONS[rr_label]
    usd_jpy = st.number_input("USDJPY conversion", min_value=1.0, value=150.0, step=0.1)
    aud_usd = st.number_input("AUDUSD conversion", min_value=0.1, value=0.65, step=0.01)

    st.divider()
    st.subheader("Strategy Settings")
    atr_mult = st.selectbox("ATR safety buffer", [0.5, 1.0, 1.5, 2.0], index=1)
    swing_len = st.selectbox("SMC swing sensitivity", [2, 3, 4, 5], index=1)
    strict_mode = st.checkbox("SMC strict Daily + 1H alignment", value=True)

    st.divider()
    st.subheader("Cameroon Watch Time")
    enforce_session = st.checkbox("Only allow signals during watch time", value=True)
    session_start = st.selectbox("Start", list(range(0, 24)), index=6, format_func=lambda x: f"{x:02d}:00 Cameroon")
    session_end = st.selectbox("Stop", list(range(1, 25)), index=21, format_func=lambda x: f"{x if x < 24 else 0:02d}:00 Cameroon")

    st.divider()
    st.subheader("Backtest")
    run_backtest = st.checkbox("Run backtest", value=True)
    max_hold = st.selectbox("Max hold 15m candles", [8, 16, 32, 48, 96], index=2)

    if st.button("Refresh Market Data"):
        st.cache_data.clear()
        st.rerun()

pages = ["Dashboard", "Analysis", "Trade Ticket", "Journal", "Performance"]
pcols = st.columns(len(pages))
for i, p in enumerate(pages):
    label = "✅ " + p if st.session_state["page"] == p else p
    if pcols[i].button(label, use_container_width=True, key=f"page_{p}"):
        st.session_state["page"] = p
        st.rerun()

st.divider()

journal = load_journal()

# Load specific strategy data for Analysis tab
analysis_error = None
daily = h1 = m15 = pd.DataFrame()
latest = None
trades_bt = pd.DataFrame()
equity_bt = pd.DataFrame()

if strategy != "Manual Risk Calculator":
    try:
        daily, h1, raw15 = load_market_data(market, str(daily_start))
        if daily.empty or h1.empty or raw15.empty:
            analysis_error = "Not enough market data returned. Try another market or refresh."

        if analysis_error is None:
            if strategy == "SMC Market Structure":
                daily, h1, m15 = build_smc_strategy(daily, h1, raw15, rr_ratio, atr_mult, swing_len, strict_mode, session_start, session_end, enforce_session)
            else:
                daily, h1, m15 = build_fx15_strategy(daily, h1, raw15, rr_ratio, atr_mult, session_start, session_end, enforce_session)

            valid = m15.dropna(subset=["Close"])
            if not valid.empty: latest = valid.iloc[-1]
            if run_backtest: trades_bt, equity_bt = backtest_signals(m15, market, account_balance, risk_percent, max_hold)
    except Exception as e:
        analysis_error = str(e)


# =====================================================
# DASHBOARD PAGE (PRO LIVE SCANNER + TELEGRAM)
# =====================================================

if st.session_state["page"] == "Dashboard":
    st.subheader(f"Live Multi-Symbol Scanner ({strategy})")
    st.caption("Auto-refreshes every 60s. Telegram alerts are sent for new valid signals.")

    if strategy == "Manual Risk Calculator":
        st.info("Scanner disabled in Manual Risk Calculator mode. Select an automated strategy.")
    else:
        cols = st.columns(min(len(PAIRS), 4))
        table = []
        
        recent_start = str(date.today() - pd.Timedelta(days=14))

        # 1. Define a helper function for the thread pool
        def fetch_pair_data(pair_name):
            try:
                d, h, m = load_market_data(pair_name, recent_start)
                return pair_name, d, h, m
            except Exception:
                return pair_name, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # 2. Fetch all market data concurrently (Limits to 5 workers to avoid Yahoo IP bans)
        with st.spinner("Scanning markets concurrently..."):
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                fetched_data = list(executor.map(fetch_pair_data, PAIRS.keys()))

        # 3. Process the results instantly
        for i, (name, scan_d, scan_h, scan_m) in enumerate(fetched_data):
            config = PAIRS[name]
            
            if scan_d.empty or scan_h.empty or scan_m.empty: 
                continue

            try:
                if strategy == "SMC Market Structure":
                    _, _, scan_res = build_smc_strategy(scan_d, scan_h, scan_m, rr_ratio, atr_mult, swing_len, strict_mode, session_start, session_end, enforce_session)
                else:
                    _, _, scan_res = build_fx15_strategy(scan_d, scan_h, scan_m, rr_ratio, atr_mult, session_start, session_end, enforce_session)
                
                scan_valid = scan_res.dropna(subset=["Close"])
                if scan_valid.empty: continue
                
                row = scan_valid.iloc[-1]
                sig = row.get("Signal", "NEUTRAL")
                price = row["Close"]
                
                col_idx = i % 4
                with cols[col_idx]:
                    st.metric(name, f"{price:.{config['decimals']}f}")
                    if sig == "BUY": st.success("BUY")
                    elif sig == "SELL": st.error("SELL")
                    else: st.warning("NEUTRAL")

                # Telegram logic
                prev = st.session_state["last_alert"].get(name)
                if sig in ["BUY", "SELL"] and sig != prev:
                    msg = f"🔥 {strategy} Alert\nSymbol: {name}\nSignal: {sig}\nPrice: {price:.{config['decimals']}f}\nTime: {datetime.now().strftime('%H:%M')}"
                    send_alert(msg)
                    st.session_state["last_alert"][name] = sig

                table.append({
                    "Symbol": name,
                    "Price": round(price, config["decimals"]),
                    "Signal": sig,
                    "Reason": row.get("Reason", "")
                })
            except Exception as e:
                pass
                
                if scan_d.empty or scan_h.empty or scan_m.empty: continue

                if strategy == "SMC Market Structure":
                    _, _, scan_res = build_smc_strategy(scan_d, scan_h, scan_m, rr_ratio, atr_mult, swing_len, strict_mode, session_start, session_end, enforce_session)
                else:
                    _, _, scan_res = build_fx15_strategy(scan_d, scan_h, scan_m, rr_ratio, atr_mult, session_start, session_end, enforce_session)
                
                scan_valid = scan_res.dropna(subset=["Close"])
                if scan_valid.empty: continue
                
                row = scan_valid.iloc[-1]
                sig = row.get("Signal", "NEUTRAL")
                price = row["Close"]
                
                col_idx = i % 4
                with cols[col_idx]:
                    st.metric(name, f"{price:.{config['decimals']}f}")
                    if sig == "BUY": st.success("BUY")
                    elif sig == "SELL": st.error("SELL")
                    else: st.warning("NEUTRAL")

                # Telegram logic
                prev = st.session_state["last_alert"].get(name)
                if sig in ["BUY", "SELL"] and sig != prev:
                    msg = f"🔥 {strategy} Alert\nSymbol: {name}\nSignal: {sig}\nPrice: {price:.{config['decimals']}f}\nTime: {datetime.now().strftime('%H:%M')}"
                    send_alert(msg)
                    st.session_state["last_alert"][name] = sig

                table.append({
                    "Symbol": name,
                    "Price": round(price, config["decimals"]),
                    "Signal": sig,
                    "Reason": row.get("Reason", "")
                })
            except Exception as e:
                pass

        st.subheader("Market Overview")
        st.dataframe(color_rows(pd.DataFrame(table)), use_container_width=True)

        st.subheader("Journal Snapshot")
        if journal.empty: st.info("No trades recorded yet.")
        else: st.dataframe(color_rows(journal.sort_values("Trade_ID", ascending=False).head(10)), use_container_width=True)


# =====================================================
# ANALYSIS PAGE
# =====================================================

elif st.session_state["page"] == "Analysis":
    st.subheader(f"{strategy} Analysis - {market}")

    if strategy == "Manual Risk Calculator":
        st.info("Manual Risk Calculator has no strategy signal. Go to Trade Ticket.")
    elif analysis_error:
        st.error(analysis_error)
    else:
        if latest is not None:
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Signal", latest.get("Signal", "NEUTRAL"))
            s2.metric("Direction", latest.get("Direction", "NEUTRAL"))
            s3.metric("Entry", fmt_price(market, latest.get("Entry", np.nan)))
            s4.metric("SL", fmt_price(market, latest.get("SL", np.nan)))
            s5.metric("TP", fmt_price(market, latest.get("TP", np.nan)))

            if latest.get("Signal", "NEUTRAL") in ["BUY", "SELL"] and pd.notna(latest.get("Entry", np.nan)):
                if st.button("Send Latest Signal to Trade Ticket", type="primary"):
                    send_to_ticket(strategy, market, latest, risk_percent, rr_label)
            else:
                st.warning("No active BUY/SELL signal right now.")

        st.plotly_chart(candle_chart(m15.tail(250), market, f"{market} 15m Chart - {strategy}"), use_container_width=True)

        setups = m15[m15["Signal"].isin(["BUY", "SELL"])].dropna(subset=["Entry", "SL", "TP"]).tail(50)
        st.subheader("Latest Valid Setups")
        if setups.empty: st.warning("No valid setups found.")
        else:
            cols = [c for c in ["Date", "Cameroon_Time", "Trading_Window", "Strategy", "Signal", "Direction", "Daily_Bias", "H1_Structure", "Premium_Discount", "Entry", "SL", "TP", "Reason"] if c in setups.columns]
            st.dataframe(color_rows(setups[cols]), use_container_width=True)
            sel = st.selectbox("Choose setup to send to Ticket", list(setups.index), index=len(setups.index) - 1)
            if st.button("Send Selected Setup to Trade Ticket"):
                send_to_ticket(strategy, market, setups.loc[sel], risk_percent, rr_label)

        if run_backtest:
            st.subheader("Backtest Trades")
            if trades_bt.empty: st.info("No backtest trades found.")
            else:
                st.dataframe(color_rows(trades_bt.tail(100)), use_container_width=True)
                st.plotly_chart(equity_chart(equity_bt), use_container_width=True)


# =====================================================
# TRADE TICKET PAGE
# =====================================================

elif st.session_state["page"] == "Trade Ticket":
    st.subheader("Trade Ticket / Risk Calculator")

    ticket = st.session_state.get("ticket", {})
    default_strategy = ticket.get("Strategy", strategy)
    default_market = ticket.get("Market", market)
    default_direction = ticket.get("Direction", "BUY")

    live_price, source = get_live_price(default_market)
    entry_default = ticket.get("Entry", live_price) if not pd.isna(ticket.get("Entry", live_price)) else live_price
    sl_default = ticket.get("SL", np.nan)
    tp_default = ticket.get("TP", np.nan)

    t1, t2, t3, t4 = st.columns(4)
    trade_strategy = t1.selectbox("Strategy", ["SMC Market Structure", "FX 15m Momentum", "Manual Risk Calculator"], index=["SMC Market Structure", "FX 15m Momentum", "Manual Risk Calculator"].index(default_strategy) if default_strategy in ["SMC Market Structure", "FX 15m Momentum", "Manual Risk Calculator"] else 0)
    trade_market = t2.selectbox("Market", list(PAIRS.keys()), index=list(PAIRS.keys()).index(default_market))
    direction = t3.selectbox("Direction", ["BUY", "SELL"], index=["BUY", "SELL"].index(default_direction) if default_direction in ["BUY", "SELL"] else 0)
    risk_pct = t4.number_input("Risk %", min_value=0.01, max_value=10.0, value=float(ticket.get("Risk_Percent", risk_percent)), step=0.25)

    step, fmt = price_step(trade_market), price_fmt(trade_market)
    if trade_market != default_market:
        entry_default, source = get_live_price(trade_market)
        sl_default, tp_default = np.nan, np.nan

    r1, r2, r3, r4 = st.columns(4)
    entry = r1.number_input("Entry Price", value=float(entry_default), step=step, format=fmt)
    rr_ticket_label = r2.selectbox("Risk Reward", list(RR_OPTIONS.keys()), index=list(RR_OPTIONS.keys()).index(ticket.get("Risk_Reward", rr_label)) if ticket.get("Risk_Reward", rr_label) in RR_OPTIONS else 2)
    rr_ticket = RR_OPTIONS[rr_ticket_label]

    presets = stop_presets(trade_market)
    preset_name = r3.selectbox("SL Distance Profile", list(presets.keys()), index=1)
    auto_sl, auto_tp = sl_tp_from_distance(direction, entry, presets[preset_name], rr_ticket)

    use_strategy_sl_tp = False
    if pd.notna(sl_default) and pd.notna(tp_default): use_strategy_sl_tp = r4.checkbox("Use strategy SL/TP", value=True)
    else: r4.caption("Using profile SL/TP")

    sl, tp = (float(sl_default), float(tp_default)) if use_strategy_sl_tp else (auto_sl, auto_tp)

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Stop Loss", fmt_price(trade_market, sl))
    p2.metric("Take Profit", fmt_price(trade_market, tp))

    try:
        pos = calc_position(trade_market, direction, entry, sl, tp, account_balance, risk_pct, usd_jpy, aud_usd)
        p3.metric("Lot Size", f"{pos['lot_size']:.4f}")
        p4.metric("Risk Amount", f"${pos['risk_amount']:.2f}")
        p5.metric("Position Size", f"{pos['position_size']:.4f}")
    except Exception as e:
        pos = None
        st.error(str(e))

    st.divider()
    st.subheader("Record Trade")

    j1, j2, j3, j4 = st.columns(4)
    trade_date = j1.date_input("Trade date", value=date.today())
    session = j2.selectbox("Session", ["London", "New York", "Asia", "London + New York", "Other"])
    result = j3.selectbox("Result", ["Open", "Win", "Loss", "Breakeven", "Timeout Positive", "Timeout Negative"])
    exit_reason = j4.selectbox("Exit Reason", ["Open", "TP", "SL", "TIME OUT", "Manual Close", "Other"])

    j5, j6, j7 = st.columns(3)
    exit_price = j5.number_input("Exit Price", value=0.0, step=step, format=fmt)
    emotion = j6.selectbox("Emotion", ["Calm", "Confident", "Fearful", "Greedy", "Frustrated", "Revenge trading", "Other"])
    mistake = j7.selectbox("Mistake", ["None", "Entered too early", "Entered too late", "Moved SL", "Over-risked", "Ignored trend", "Ignored news", "Revenge trade", "Other"])
    notes = st.text_area("Notes", value=ticket.get("Reason", ""))

    if st.button("Save Trade", type="primary", disabled=(pos is None)):
        pnl, r_mult = np.nan, np.nan
        if result != "Open" and exit_price != 0 and pos is not None:
            pnl, r_mult = calc_pnl(direction, entry, exit_price, pos["position_size"], pos["risk_amount"])

        new_row = {
            "Trade_ID": next_trade_id(journal), "Date": trade_date, "Strategy": trade_strategy,
            "Market": trade_market, "Direction": direction, "Signal": ticket.get("Signal", direction),
            "Session": session, "Entry": entry, "Stop_Loss": sl, "Take_Profit": tp,
            "Risk_Percent": risk_pct, "Risk_Amount": pos["risk_amount"], "Lot_Size": pos["lot_size"],
            "Position_Size": pos["position_size"], "Risk_Reward": rr_ticket_label, "Result": result,
            "Exit_Price": np.nan if exit_price == 0 else exit_price, "Exit_Reason": exit_reason,
            "PnL": pnl, "R_Multiple": r_mult, "Emotion": emotion, "Mistake": mistake, "Notes": notes,
        }
        journal = pd.concat([journal, pd.DataFrame([new_row])], ignore_index=True)
        save_journal(journal)
        
        # Send Telegram notification for manual execution
        send_alert(f"🟢 TRADE EXECUTED\nSymbol: {trade_market}\nDirection: {direction}\nEntry: {entry}\nSL: {sl}\nTP: {tp}\nRisk: {risk_pct}%\nLot: {pos['lot_size']:.2f}")

        if "ticket" in st.session_state: del st.session_state["ticket"]
        st.success("Trade recorded and alert sent.")
        st.rerun()


# =====================================================
# JOURNAL PAGE
# =====================================================

elif st.session_state["page"] == "Journal":
    st.subheader("Trading Journal")

    if journal.empty: st.info("No trades recorded yet.")
    else:
        st.dataframe(color_rows(journal.sort_values("Trade_ID", ascending=False)), use_container_width=True)
        st.download_button("Download Journal CSV", journal.to_csv(index=False).encode("utf-8"), "unified_trading_journal.csv", "text/csv")

        st.divider()
        st.subheader("Edit Saved Trade")
        ids = pd.to_numeric(journal["Trade_ID"], errors="coerce").dropna().astype(int).sort_values(ascending=False).tolist()
        selected_id = st.selectbox("Select Trade ID", ids)
        idx = journal[journal["Trade_ID"] == selected_id].index[0]
        row = journal.loc[idx]

        e1, e2, e3, e4 = st.columns(4)
        edit_result = e1.selectbox("Result", ["Open", "Win", "Loss", "Breakeven", "Timeout Positive", "Timeout Negative"], index=["Open", "Win", "Loss", "Breakeven", "Timeout Positive", "Timeout Negative"].index(row["Result"]) if row["Result"] in ["Open", "Win", "Loss", "Breakeven", "Timeout Positive", "Timeout Negative"] else 0)
        edit_reason = e2.selectbox("Exit Reason", ["Open", "TP", "SL", "TIME OUT", "Manual Close", "Other"], index=["Open", "TP", "SL", "TIME OUT", "Manual Close", "Other"].index(row["Exit_Reason"]) if row["Exit_Reason"] in ["Open", "TP", "SL", "TIME OUT", "Manual Close", "Other"] else 0)
        
        edit_market = row["Market"] if row["Market"] in PAIRS else market
        edit_step, edit_fmt = price_step(edit_market), price_fmt(edit_market)
        current_exit = 0.0 if pd.isna(row["Exit_Price"]) else float(row["Exit_Price"])
        edit_exit = e3.number_input("Exit Price", value=current_exit, step=edit_step, format=edit_fmt)
        edit_notes = st.text_area("Notes", value="" if pd.isna(row["Notes"]) else str(row["Notes"]))

        if st.button("Update Trade", type="primary"):
            pnl, r_mult = np.nan, np.nan
            if edit_result != "Open" and edit_exit != 0:
                pnl, r_mult = calc_pnl(row["Direction"], float(row["Entry"]), edit_exit, float(row["Position_Size"]), float(row["Risk_Amount"]))
            journal.loc[idx, "Result"] = edit_result
            journal.loc[idx, "Exit_Reason"] = edit_reason
            journal.loc[idx, "Exit_Price"] = np.nan if edit_exit == 0 else edit_exit
            journal.loc[idx, "PnL"], journal.loc[idx, "R_Multiple"], journal.loc[idx, "Notes"] = pnl, r_mult, edit_notes
            save_journal(journal)
            st.success("Trade updated.")
            st.rerun()

        if st.button("Delete Selected Trade"):
            journal = journal[journal["Trade_ID"] != selected_id]
            save_journal(journal)
            st.success("Trade deleted.")
            st.rerun()


# =====================================================
# PERFORMANCE PAGE
# =====================================================

elif st.session_state["page"] == "Performance":
    st.subheader("Performance Dashboard")

    if journal.empty: st.info("No performance data yet.")
    else:
        df = journal.copy()
        df["PnL"] = pd.to_numeric(df["PnL"], errors="coerce")
        df["R_Multiple"] = pd.to_numeric(df["R_Multiple"], errors="coerce")
        closed = df[df["Result"].isin(["Win", "Loss", "Breakeven", "Timeout Positive", "Timeout Negative"])].copy()

        total = len(closed)
        wins = len(closed[closed["PnL"] > 0])
        win_rate = wins / total * 100 if total else 0
        net_pnl = closed["PnL"].sum() if total else 0
        net_r = closed["R_Multiple"].sum() if total else 0
        avg_r = closed["R_Multiple"].mean() if total else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Closed Trades", total)
        m2.metric("Win Rate", f"{win_rate:.2f}%")
        m3.metric("Net PnL", f"${net_pnl:.2f}")
        m4.metric("Net R", f"{net_r:.2f}R")
        m5.metric("Average R", f"{avg_r:.2f}R")

        equity, trade_axis, bal = [account_balance], [0], account_balance
        for _, r in closed.sort_values("Trade_ID").iterrows():
            if pd.notna(r["PnL"]): bal += r["PnL"]
            equity.append(bal); trade_axis.append(r["Trade_ID"])

        st.plotly_chart(equity_chart(pd.DataFrame({"Trade": trade_axis, "Balance": equity})), use_container_width=True)

        st.subheader("Performance by Strategy")
        st.dataframe(color_rows(closed.groupby("Strategy").agg(Trades=("Trade_ID", "count"), Net_PnL=("PnL", "sum"), Avg_R=("R_Multiple", "mean")).reset_index()), use_container_width=True)

        st.subheader("Performance by Market")
        st.dataframe(color_rows(closed.groupby("Market").agg(Trades=("Trade_ID", "count"), Net_PnL=("PnL", "sum"), Avg_R=("R_Multiple", "mean")).reset_index()), use_container_width=True)

st.warning("Educational and journaling tool only. It does not guarantee profitable trades. Confirm all prices and execution in your broker platform.")