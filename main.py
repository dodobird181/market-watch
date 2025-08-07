import datetime
import time
from typing import Any

import requests
from decouple import config

FRED_API_KEY = config("FRED_API_KEY", cast=str)

LOG_FILE = config("LOG_FILE", default="market_triggers.log", cast=str)
CHECK_INTERVAL_MINUTES = config("CHECK_INTERVAL_MINUTES", default=30, cast=int)


class HTTPError(Exception):

    def __init__(self, status: int, message: str | None = None):
        super().__init__()
        self.status = status
        self.message = message

    def __str__(self) -> str:
        if not self.message:
            return f"<HTTPError: status={self.status}>"
        return f'<HTTPError: status={self.status}, message="{self.message}">'


def log(message):
    """Append a timestamped message to the logfile."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    timestamp = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")


def get(url: str, timeout=30) -> dict[str, Any]:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    if response.status_code != 200:
        raise HTTPError(status=response.status_code, message=str(response.content))
    return response.json()


def check_vix():
    """Fetch current VIX index level."""
    try:
        data = get("https://query1.finance.yahoo.com/v8/finance/chart/^VIX")
        vix = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return vix
    except Exception as e:
        log(f"Error fetching VIX: {e.with_traceback(None)}")
        return None


def check_sp500_200ma():
    """Check if S&P 500 is above or below 200-day moving average."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=1y&interval=1d"
        closes = get(url)["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) >= 200:
            ma200 = sum(closes[-200:]) / 200
            last_price = closes[-1]
            return last_price, ma200
        return None
    except Exception as e:
        log(f"Error fetching S&P 500 data: {e}")
        return None


def check_yield_curve():
    """Fetch 2-year and 10-year Treasury yields from FRED."""
    if not FRED_API_KEY:
        return None
    try:
        url_2y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS2&api_key={FRED_API_KEY}&file_type=json"
        url_10y = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={FRED_API_KEY}&file_type=json"
        data_2y = requests.get(url_2y).json()["observations"][-1]
        data_10y = requests.get(url_10y).json()["observations"][-1]
        y2 = float(data_2y["value"])
        y10 = float(data_10y["value"])
        spread = y10 - y2
        return y2, y10, spread
    except Exception as e:
        log(f"Error fetching yield curve: {e}")
        return None


# ===== MAIN LOOP =====
def run_monitor():
    log("=== Market Trigger Monitor Started ===")
    while True:
        # VIX check
        vix = check_vix()
        if vix:
            if vix > 45:
                log(f"VIX ALERT: {vix} (Possible Capitulation Trigger)")
            elif vix > 25:
                log(f"VIX Warning: {vix} (Crash Phase Trigger)")
            else:
                log(f"VIX Normal: {vix}")

        # S&P 500 check
        sp500 = check_sp500_200ma()
        if sp500:
            price, ma200 = sp500
            if price < ma200:
                log(f"S&P 500 Below 200MA: Price={price:.2f}, MA200={ma200:.2f}")
            else:
                log(f"S&P 500 Above 200MA: Price={price:.2f}, MA200={ma200:.2f}")

        # Yield curve check
        yc = check_yield_curve()
        if yc:
            y2, y10, spread = yc
            if spread < -0.75:
                log(
                    f"Yield Curve Deep Inversion: 2y={y2}%, 10y={y10}%, Spread={spread:.2f}%"
                )
            else:
                log(f"Yield Curve Normal/Steepening: Spread={spread:.2f}%")

        # Wait until next check
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    run_monitor()
