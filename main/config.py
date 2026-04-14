# config.py

SEARCH_URL_DDG = "https://html.duckduckgo.com/html/"
SEARCH_URL_ALLDATASHEET = "https://www.alldatasheet.com/view.jsp"
SEARCH_URL_DATASHEETSPDF = "https://datasheetspdf.com/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 25
MAX_RETRIES = 2
RETRY_BACKOFF_FACTOR = 1.5

# Параметры параллелизма
MAX_WORKERS_PER_SOURCE = 3   # одновременных запросов к одному источнику
MAX_WORKERS_TOTAL = 5        # одновременно обрабатываемых деталей