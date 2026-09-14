import io
import logging

logger = logging.getLogger(__name__)


def generate_price_chart(df, title="Gold 18K Price"):
    """ساخت نمودار قیمت طلا (lazy import matplotlib)."""
    if df.empty or len(df) < 2:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        logger.error(f"Matplotlib import failed: {e}")
        return None

    try:
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(10, 6),
            gridspec_kw={"height_ratios": [3, 1]},
            sharex=True
        )

        x = range(len(df))
        prices = df["close"].values

        ax1.plot(x, prices, color="#2E86DE", linewidth=2, label="Close")

        if len(df) >= 20:
            ema20 = df["close"].ewm(span=20, adjust=False).mean().values
            ax1.plot(x, ema20, color="#F39C12", linewidth=1,
                     label="EMA 20", alpha=0.8)

        if len(df) >= 50:
            ema50 = df["close"].ewm(span=50, adjust=False).mean().values
            ax1.plot(x, ema50, color="#E74C3C", linewidth=1,
                     label="EMA 50", alpha=0.8)

        ax1.set_title(title, fontsize=14, fontweight="bold")
        ax1.set_ylabel("Price (Toman)")
        ax1.legend(loc="upper left", fontsize=9)
        ax1.grid(True, alpha=0.3)
        ax1.ticklabel_format(style="plain", axis="y")

        if len(df) >= 15:
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)
            avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, float("nan"))
            rsi = 100 - (100 / (1 + rs))

            ax2.plot(x, rsi.values, color="#8E44AD", linewidth=1.5)
            ax2.axhline(70, color="red", linestyle="--", alpha=0.5, linewidth=1)
            ax2.axhline(30, color="green", linestyle="--", alpha=0.5, linewidth=1)
            ax2.set_ylabel("RSI")
            ax2.set_ylim(0, 100)
            ax2.grid(True, alpha=0.3)

        if hasattr(df.index, "strftime"):
            step = max(1, len(df) // 6)
            ticks = list(range(0, len(df), step))
            labels = [df.index[i].strftime("%m-%d %H:%M") for i in ticks]
            ax2.set_xticks(ticks)
            ax2.set_xticklabels(labels, rotation=30, fontsize=8)

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100)
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        logger.error(f"Chart generation failed: {e}", exc_info=True)
        return None
