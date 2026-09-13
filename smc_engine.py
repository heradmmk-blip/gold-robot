import pandas as pd
import logging
from smartmoneyconcepts import smc
from config import SWING_LENGTH

logger = logging.getLogger(__name__)


def prepare_ohlc(df):
    ohlc = df[["open", "high", "low", "close"]].copy()
    ohlc.columns = ["open", "high", "low", "close"]
    return ohlc.reset_index(drop=True)


def compute_smc_score(df):
    if df.empty or len(df) < 30:
        return {"score": 0.5, "details": {"error": "داده کافی نیست"}}
    ohlc = prepare_ohlc(df)
    signals = []
    details = {}

    try:
        swing_hl = smc.swing_highs_lows(ohlc, swing_length=SWING_LENGTH)
        bos = smc.bos_choch(ohlc, swing_hl, close_break=True)
        if not bos.empty:
            last = bos.iloc[-1]
            bv = last.get("BOS", 0)
            cv = last.get("CHOCH", 0)
            if bv == 1:
                signals.append(("bos", 0.85, 0.30))
                details["bos"] = "شکست ساختار صعودی (BOS)"
            elif bv == -1:
                signals.append(("bos", 0.15, 0.30))
                details["bos"] = "شکست ساختار نزولی (BOS)"
            elif cv == 1:
                signals.append(("choch", 0.80, 0.25))
                details["choch"] = "تغییر کاراکتر صعودی (CHoCH)"
            elif cv == -1:
                signals.append(("choch", 0.20, 0.25))
                details["choch"] = "تغییر کاراکتر نزولی (CHoCH)"
    except Exception as e:
        logger.warning(f"BOS failed: {e}")

    try:
        swing_hl = smc.swing_highs_lows(ohlc, swing_length=SWING_LENGTH)
        ob = smc.ob(ohlc, swing_hl, close_mitigation=False)
        current = ohlc["close"].iloc[-1]
        if not ob.empty:
            active = ob[ob["MitigatedIndex"].isna()] if "MitigatedIndex" in ob.columns else ob
            for _, row in active.iterrows():
                top = row.get("Top", 0)
                bot = row.get("Bottom", 0)
                typ = row.get("OB", 0)
                if bot <= current <= top * 1.01:
                    if typ == 1:
                        signals.append(("ob_bull", 0.80, 0.25))
                        details["order_block"] = f"OB صعودی ({bot:,.0f}-{top:,.0f})"
                    elif typ == -1:
                        signals.append(("ob_bear", 0.20, 0.25))
                        details["order_block"] = f"OB نزولی ({bot:,.0f}-{top:,.0f})"
                    break
    except Exception as e:
        logger.warning(f"OB failed: {e}")

    try:
        fvg = smc.fvg(ohlc, join_consecutive=True)
        if not fvg.empty:
            last = fvg.iloc[-1]
            t = last.get("FVG", 0)
            top = last.get("Top", 0)
            bot = last.get("Bottom", 0)
            if t == 1:
                signals.append(("fvg_bull", 0.75, 0.20))
                details["fvg"] = f"FVG صعودی ({bot:,.0f}-{top:,.0f})"
            elif t == -1:
                signals.append(("fvg_bear", 0.25, 0.20))
                details["fvg"] = f"FVG نزولی ({bot:,.0f}-{top:,.0f})"
    except Exception as e:
        logger.warning(f"FVG failed: {e}")

    if not signals:
        return {"score": 0.5, "details": {"info": "سیگنال SMC واضح نیست"}}
    tw = sum(w for _, _, w in signals)
    return {"score": round(sum(s * w for _, s, w in signals) / tw, 4),
            "details": details}
