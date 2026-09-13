import requests
import pandas as pd
import sqlite3
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from config import DB_PATH, BRS_API_KEY

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_gold_18k_tgju():
    try:
        url = "https://www.tgju.org/profile/geram18"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        tag = soup.select_one("span#l-price_dollar_rl") or \
              soup.select_one("span[data-col='info.last_trade.PDrCotVal']")
        if tag:
            price = float(tag.get_text(strip=True).replace(",", ""))
            return {"price": price, "change": 0.0, "source": "tgju",
                    "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"TGJU failed: {e}")
    return None


def fetch_gold_navasan():
    try:
        url = ("https://raw.githubusercontent.com/HosseinOdd/"
               "Navasan-API/main/data/gold.json")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            for key, val in data.items():
                if "18" in str(key) and "gold" in str(key).lower():
                    p = val.get("price", val) if isinstance(val, dict) else val
                    return {"price": float(p), "change": 0.0, "source": "navasan",
                            "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"Navasan failed: {e}")
    return None


def fetch_gold_brsapi():
    if not BRS_API_KEY:
        return None
    try:
        url = f"https://BrsApi.ir/Api/Market/Gold_Currency.php?key={BRS_API_KEY}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("gold", []):
            if "18" in str(item.get("name", "")):
                return {"price": float(item.get("price", 0)),
                        "change": float(item.get("change", 0)),
                        "source": "brsapi",
                        "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"BrsApi failed: {e}")
    return None


def fetch_gold_ounce():
    try:
        resp = requests.get("https://data-asg.goldprice.org/dbXRates/USD",
                            headers=HEADERS, timeout=10)
        data = resp.json()
        price = data["items"][0]["xauPrice"]
        return {"price": float(price),
                "change": float(data["items"][0].get("chgXau", 0)),
                "source": "goldprice.org",
                "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"goldprice.org failed: {e}")
    try:
        resp = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
                            headers=HEADERS, timeout=10)
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta.get("chartPreviousClose", price)
        return {"price": float(price), "change": float(price - prev),
                "source": "yahoo", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"Yahoo failed: {e}")
    return None


def fetch_usd_irr():
    try:
        url = "https://www.tgju.org/profile/price_dollar_rl"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")
        tag = soup.select_one("span#l-price_dollar_rl") or \
              soup.select_one("span[data-col='info.last_trade.PDrCotVal']")
        if tag:
            price = float(tag.get_text(strip=True).replace(",", ""))
            return {"price": price, "source": "tgju",
                    "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"USD fetch failed: {e}")
    return None


def fetch_dxy():
    try:
        resp = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
                            headers=HEADERS, timeout=10)
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev = meta.get("chartPreviousClose", price)
        return {"price": float(price), "change": float(price - prev),
                "source": "yahoo", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.warning(f"DXY failed: {e}")
    return None


def fetch_all_data():
    data = {}
    data["gold_18k"] = (fetch_gold_brsapi() or fetch_gold_18k_tgju()
                        or fetch_gold_navasan())
    data["gold_ounce"] = fetch_gold_ounce()
    data["usd"] = fetch_usd_irr()
    data["dxy"] = fetch_dxy()
    return data


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gold_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            gold_18k REAL,
            gold_ounce REAL,
            usd_irr REAL,
            dxy REAL,
            source_18k TEXT,
            source_ounce TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ دیتابیس آماده شد")


def save_price_data(data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    gold = data.get("gold_18k") or {}
    ounce = data.get("gold_ounce") or {}
    usd = data.get("usd") or {}
    dxy = data.get("dxy") or {}
    cursor.execute("""
        INSERT INTO gold_prices
            (timestamp, gold_18k, gold_ounce, usd_irr, dxy, source_18k, source_ounce)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(),
          gold.get("price"), ounce.get("price"),
          usd.get("price"), dxy.get("price"),
          gold.get("source"), ounce.get("source")))
    conn.commit()
    conn.close()


def get_historical_data(days=90):
    conn = sqlite3.connect(DB_PATH)
    query = f"""
        SELECT timestamp, gold_18k, gold_ounce, usd_irr, dxy
        FROM gold_prices
        WHERE timestamp >= datetime('now', '-{days} days')
        ORDER BY timestamp ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    df.dropna(subset=["gold_18k"], inplace=True)
    df["open"] = df["gold_18k"].shift(1).fillna(df["gold_18k"])
    df["high"] = df["gold_18k"]
    df["low"] = df["gold_18k"]
    df["close"] = df["gold_18k"]
    df["volume"] = 0
    return df
