import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# سطوح حمایت و مقاومت
# ══════════════════════════════════════════════
def find_pivot_points(df, window=5):
    """پیدا کردن نقاط پیوت (سقف و کف محلی)."""
    highs = df["high"].values
    lows = df["low"].values

    pivot_highs = []
    pivot_lows = []

    for i in range(window, len(df) - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            pivot_highs.append(highs[i])
        if lows[i] == min(lows[i - window:i + window + 1]):
            pivot_lows.append(lows[i])

    return pivot_highs, pivot_lows


def find_support_resistance(df, current_price, max_levels=3):
    """پیدا کردن نزدیک‌ترین سطوح حمایت و مقاومت."""
    if df.empty or len(df) < 20:
        return {"supports": [], "resistances": []}

    pivot_highs, pivot_lows = find_pivot_points(df, window=5)

    supports = sorted([p for p in pivot_lows if p < current_price],
                      reverse=True)[:max_levels]
    resistances = sorted([p for p in pivot_highs if p > current_price])[:max_levels]

    return {
        "supports": [round(float(s), 0) for s in supports],
        "resistances": [round(float(r), 0) for r in resistances],
    }


# ══════════════════════════════════════════════
# الگوهای کندلی
# ══════════════════════════════════════════════
def detect_doji(row, body_threshold=0.1):
    body = abs(row["close"] - row["open"])
    total_range = row["high"] - row["low"]
    if total_range == 0:
        return False
    return body / total_range < body_threshold


def detect_hammer(row):
    body = abs(row["close"] - row["open"])
    lower_shadow = min(row["open"], row["close"]) - row["low"]
    upper_shadow = row["high"] - max(row["open"], row["close"])
    total_range = row["high"] - row["low"]

    if total_range == 0 or body == 0:
        return False

    return (lower_shadow > 2 * body and
            upper_shadow < body and
            body / total_range < 0.4)


def detect_shooting_star(row):
    body = abs(row["close"] - row["open"])
    lower_shadow = min(row["open"], row["close"]) - row["low"]
    upper_shadow = row["high"] - max(row["open"], row["close"])
    total_range = row["high"] - row["low"]

    if total_range == 0 or body == 0:
        return False

    return (upper_shadow > 2 * body and
            lower_shadow < body and
            body / total_range < 0.4)


def detect_bullish_engulfing(prev, curr):
    prev_bearish = prev["close"] < prev["open"]
    curr_bullish = curr["close"] > curr["open"]
    if not (prev_bearish and curr_bullish):
        return False
    return (curr["open"] < prev["close"] and
            curr["close"] > prev["open"])


def detect_bearish_engulfing(prev, curr):
    prev_bullish = prev["close"] > prev["open"]
    curr_bearish = curr["close"] < curr["open"]
    if not (prev_bullish and curr_bearish):
        return False
    return (curr["open"] > prev["close"] and
            curr["close"] < prev["open"])


def detect_candlestick_patterns(df, lookback=3):
    """تشخیص الگوهای کندلی در آخرین چند کندل."""
    if df.empty or len(df) < lookback + 1:
        return []

    patterns = []
    recent = df.tail(lookback + 1).reset_index(drop=True)

    last = recent.iloc[-1]
    prev = recent.iloc[-2] if len(recent) > 1 else None

    if detect_hammer(last):
        patterns.append({"name": "Hammer", "name_fa": "چکش",
                         "signal": "صعودی", "score": 0.75})

    if detect_shooting_star(last):
        patterns.append({"name": "Shooting Star", "name_fa": "ستاره ثاقب",
                         "signal": "نزولی", "score": 0.25})

    if detect_doji(last):
        patterns.append({"name": "Doji", "name_fa": "دوجی",
                         "signal": "بی‌طرف", "score": 0.5})

    if prev is not None:
        if detect_bullish_engulfing(prev, last):
            patterns.append({"name": "Bullish Engulfing", "name_fa": "پوشای صعودی",
                             "signal": "صعودی", "score": 0.8})

        if detect_bearish_engulfing(prev, last):
            patterns.append({"name": "Bearish Engulfing", "name_fa": "پوشای نزولی",
                             "signal": "نزولی", "score": 0.2})

    return patterns


def compute_pattern_score(df):
    """امتیاز ترکیبی الگوهای کندلی (۰ تا ۱)."""
    patterns = detect_candlestick_patterns(df)
    if not patterns:
        return {"score": 0.5, "patterns": [], "details": {}}

    scores = [p["score"] for p in patterns]
    avg_score = sum(scores) / len(scores)

    details = {"patterns": [p["name_fa"] for p in patterns]}

    return {"score": round(avg_score, 4),
            "patterns": patterns,
            "details": details}


def run_pattern_analysis(df, current_price):
    """تحلیل کامل الگوها + سطوح کلیدی."""
    patterns = compute_pattern_score(df)
    levels = find_support_resistance(df, current_price)

    return {
        "score": patterns["score"],
        "patterns": patterns["patterns"],
        "supports": levels["supports"],
        "resistances": levels["resistances"],
        "details": patterns["details"],
    }
