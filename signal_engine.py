import logging
from datetime import datetime
from config import (WEIGHTS, BULLISH_THRESHOLD, BEARISH_THRESHOLD,
                    ALERT_COOLDOWN_MINUTES)

logger = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self):
        self.last_alert_time = None
        self.last_alert_direction = None

    def combine(self, technical, fundamental, smc):
        t = technical.get("score", 0.5)
        f = fundamental.get("score", 0.5)
        s = smc.get("score", 0.5)
        combined = round(t * WEIGHTS["technical"] +
                         f * WEIGHTS["fundamental"] +
                         s * WEIGHTS["smc"], 4)
        if combined >= BULLISH_THRESHOLD:
            direction = "صعودی"
            conf = combined * 100
        elif combined <= BEARISH_THRESHOLD:
            direction = "نزولی"
            conf = (1 - combined) * 100
        else:
            direction = "بی‌طرف"
            conf = max(combined, 1 - combined) * 100
        return {"direction": direction,
                "confidence": round(conf, 1),
                "combined_score": combined,
                "technical_score": t,
                "fundamental_score": f,
                "smc_score": s,
                "timestamp": datetime.now().isoformat(),
                "details": {"technical": technical.get("details", {}),
                            "fundamental": fundamental.get("details", {}),
                            "smc": smc.get("details", {})}}

    def should_alert(self, signal):
        if signal["direction"] == "بی‌طرف":
            return False
        if signal["confidence"] < 60:
            return False
        now = datetime.now()
        if self.last_alert_time and self.last_alert_direction == signal["direction"]:
            elapsed = (now - self.last_alert_time).total_seconds() / 60
            if elapsed < ALERT_COOLDOWN_MINUTES:
                return False
        self.last_alert_time = now
        self.last_alert_direction = signal["direction"]
        return True

    def format_message(self, signal, price):
        d = signal["direction"]
        emoji = "🟢📈" if d == "صعودی" else "🔴📉" if d == "نزولی" else "⚪️"
        det = signal.get("details", {})
        tech = det.get("technical", {})
        fund = det.get("fundamental", {})
        smcd = det.get("smc", {})
        lines = [
            f"{emoji} **سیگنال طلا (۱۸ عیار)**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📊 جهت: {d}",
            f"🎯 اطمینان: {signal['confidence']}%",
            f"💰 قیمت: {price:,.0f} تومان",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📈 تکنیکال: {signal['technical_score']:.2f}",
        ]
        if tech.get("ema_crossover"):
            lines.append(f"  • EMA: {tech['ema_crossover']}")
        if tech.get("rsi"):
            lines.append(f"  • RSI: {tech['rsi']} ({tech.get('rsi_status', '')})")
        if tech.get("macd_signal"):
            lines.append(f"  • MACD: {tech['macd_signal']}")
        lines.append(f"\n🌍 فاندامنتال: {signal['fundamental_score']:.2f}")
        if fund.get("usd_trend"):
            lines.append(f"  • دلار: {fund['usd_trend']}")
        if fund.get("ounce_trend"):
            lines.append(f"  • انس: {fund['ounce_trend']}")
        if fund.get("dxy_trend"):
            lines.append(f"  • DXY: {fund['dxy_trend']}")
        if fund.get("bubble"):
            lines.append(f"  • حباب: {fund['bubble']}")
        lines.append(f"\n🧠 SMC: {signal['smc_score']:.2f}")
        if smcd.get("bos"):
            lines.append(f"  • ساختار: {smcd['bos']}")
        if smcd.get("order_block"):
            lines.append(f"  • OB: {smcd['order_block']}")
        if smcd.get("fvg"):
            lines.append(f"  • FVG: {smcd['fvg']}")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"⚖️ امتیاز نهایی: {signal['combined_score']:.4f}")
        lines.append(f"🕐 {signal['timestamp'][:19]}")
        lines.append("\n⚠️ _این سیگنال کمک‌تحلیل است._")
        return "\n".join(lines)
