import pandas as pd
import numpy as np
import logging
from tradingview_ta import TA_Handler, Interval
from config import (EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT,
                    RSI_OVERSOLD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, ATR_PERIOD)

logger = logging.getLogger(__name__)


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def calculate_atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def get_tradingview_signal():
    try:
        handler = TA_Handler(symbol="XAUUSD", screener="cfd",
                             exchange="OANDA",
                             interval=Interval.INTERVAL_1_HOUR)
        analysis = handler.get_analysis()
        return {"recommendation": analysis.summary.get("RECOMMENDATION", "NEUTRAL"),
                "source": "tradingview"}
    except Exception as e:
        logger.warning(f"TV failed: {e}")
        return {"recommendation": "NEUTRAL", "source": "failed"}


def compute_technical_score(df):
    if df.empty or len(df) < 50:
        return {"score": 0.5, "details": {"error": "داده کافی نیست"}}
    close = df["close"]
    ema_fast = calculate_ema(close, EMA_FAST)
    ema_slow = calculate_ema(close, EMA_SLOW)
    ema_signal = 1.0 if ema_fast.iloc[-1] > ema_slow.iloc[-1] else 0.0
    rsi = calculate_rsi(close, RSI_PERIOD)
    rsi_val = rsi.iloc[-1]
    if rsi_val > RSI_OVERBOUGHT:
        rsi_signal = 0.2
    elif rsi_val < RSI_OVERSOLD:
        rsi_signal = 0.8
    else:
        rsi_signal = 0.5 + (rsi_val - 50) / 100
    macd_line, signal_line, hist = calculate_macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    macd_signal = 1.0 if macd_line.iloc[-1] > signal_line.iloc[-1] else 0.0
    atr = calculate_atr(df, ATR_PERIOD)
    atr_val = atr.iloc[-1]
    price_range = df["high"].max() - df["low"].min()
    adx_proxy = min(atr_val / (price_range / len(df) + 1e-9), 1.0)
    score = (ema_signal * 0.35 + rsi_signal * 0.25 +
             macd_signal * 0.25 + adx_proxy * 0.15)
    return {"score": round(float(score), 4),
            "details": {
                "ema_crossover": "صعودی" if ema_signal > 0.5 else "نزولی",
                "rsi": round(float(rsi_val), 2),
                "rsi_status": ("اشباع خرید" if rsi_val > RSI_OVERBOUGHT
                               else "اشباع فروش" if rsi_val < RSI_OVERSOLD
                               else "خنثی"),
                "macd_signal": "صعودی" if macd_signal > 0.5 else "نزولی",
            }}


def run_technical_analysis(df):
    local = compute_technical_score(df)
    tv = get_tradingview_signal()
    tv_score = 0.5
    if tv["recommendation"] == "STRONG_BUY":
        tv_score = 0.95
    elif tv["recommendation"] == "BUY":
        tv_score = 0.75
    elif tv["recommendation"] == "STRONG_SELL":
        tv_score = 0.05
    elif tv["recommendation"] == "SELL":
        tv_score = 0.25
    final = local["score"] * 0.6 + tv_score * 0.4
    return {"score": round(final, 4), "local": local, "tradingview": tv}
