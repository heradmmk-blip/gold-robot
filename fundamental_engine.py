import logging

logger = logging.getLogger(__name__)


def compute_fundamental_score(data, df_hist=None):
    details = {}
    scores = []

    usd = data.get("usd")
    if usd and df_hist is not None and len(df_hist) > 10:
        s = df_hist["usd_irr"].dropna()
        if len(s) > 10:
            ch = (s.iloc[-1] / s.iloc[-10] - 1) * 100
            if ch > 1.0:
                sc = 0.85
                details["usd_trend"] = f"صعودی ({ch:+.2f}%)"
            elif ch < -1.0:
                sc = 0.20
                details["usd_trend"] = f"نزولی ({ch:+.2f}%)"
            else:
                sc = 0.50
                details["usd_trend"] = f"خنثی ({ch:+.2f}%)"
            scores.append(("usd", sc, 0.35))

    ounce = data.get("gold_ounce")
    if ounce and df_hist is not None:
        s = df_hist["gold_ounce"].dropna()
        if len(s) > 10:
            ch = (s.iloc[-1] / s.iloc[-10] - 1) * 100
            if ch > 0.5:
                sc = 0.80
                details["ounce_trend"] = f"صعودی ({ch:+.2f}%)"
            elif ch < -0.5:
                sc = 0.25
                details["ounce_trend"] = f"نزولی ({ch:+.2f}%)"
            else:
                sc = 0.50
                details["ounce_trend"] = f"خنثی ({ch:+.2f}%)"
            scores.append(("ounce", sc, 0.30))

    dxy = data.get("dxy")
    if dxy and df_hist is not None:
        s = df_hist["dxy"].dropna()
        if len(s) > 10:
            ch = (s.iloc[-1] / s.iloc[-10] - 1) * 100
            if ch > 0.3:
                sc = 0.25
                details["dxy_trend"] = f"صعودی ({ch:+.2f}%)"
            elif ch < -0.3:
                sc = 0.80
                details["dxy_trend"] = f"نزولی ({ch:+.2f}%)"
            else:
                sc = 0.50
                details["dxy_trend"] = f"خنثی ({ch:+.2f}%)"
            scores.append(("dxy", sc, 0.20))

    if ounce and usd and data.get("gold_18k"):
        try:
            intrinsic = (ounce["price"] * usd["price"]) / 31.1035 * 0.75
            market = data["gold_18k"]["price"]
            bubble = (market / intrinsic - 1) * 100
            if bubble > 15:
                sc = 0.25
                details["bubble"] = f"حباب بالا ({bubble:+.1f}%)"
            elif bubble < -5:
                sc = 0.75
                details["bubble"] = f"زیر ارزش ({bubble:+.1f}%)"
            else:
                sc = 0.50
                details["bubble"] = f"نرمال ({bubble:+.1f}%)"
            scores.append(("bubble", sc, 0.15))
        except Exception as e:
            logger.warning(f"Bubble failed: {e}")

    if not scores:
        return {"score": 0.5, "details": {"error": "داده کافی نیست"}}
    tw = sum(w for _, _, w in scores)
    return {"score": round(sum(s * w for _, s, w in scores) / tw, 4),
            "details": details}
