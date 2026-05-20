# utils.py

import re
import time
import requests
from urllib.parse import urlparse, parse_qs, unquote
from typing import Optional
from config import MAX_RETRIES, RETRY_BACKOFF_FACTOR, REQUEST_TIMEOUT


def sanitize_filename(name: str) -> str:
    """Очищает имя файла от недопустимых символов."""
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180]


def is_pdf_by_head(url: str, session: requests.Session) -> bool:
    """Быстрая проверка Content-Type через HEAD-запрос."""
    try:
        resp = session.head(url, timeout=10, allow_redirects=True)
        ctype = resp.headers.get("Content-Type", "").lower()
        return "application/pdf" in ctype
    except Exception:
        return False


def looks_like_pdf_url(url: str) -> bool:
    """Эвристика: URL заканчивается на .pdf (игнорируя параметры)."""
    return url.lower().split("?")[0].endswith(".pdf")


def unwrap_ddg_redirect(url: str) -> str:
    """Распаковывает редирект DuckDuckGo (параметр uddg или u)."""
    parsed = urlparse(url)
    if parsed.path == "/l/":
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
        if "u" in qs and qs["u"]:
            return unquote(qs["u"][0])
    return url


def request_with_retry(
    session: requests.Session, method: str, url: str, **kwargs
) -> requests.Response:
    """Выполняет запрос с повторными попытками при сетевых ошибках."""
    retries = 0
    last_exc = None
    timeout = kwargs.pop('timeout', REQUEST_TIMEOUT)
    
    # Для DuckDuckGo используем специальные заголовки
    if "duckduckgo.com" in url:
        ddg_headers = {
            "Referer": "https://duckduckgo.com/",
            "Origin": "https://duckduckgo.com",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        existing_headers = session.headers.copy()
        existing_headers.update(ddg_headers)
        session.headers.update(ddg_headers)
    
    while retries <= MAX_RETRIES:
        try:
            resp = session.request(method, url, timeout=timeout, **kwargs)
            
            # Обработка 403 для DuckDuckGo
            if resp.status_code == 403 and "duckduckgo.com" in url:
                # Пробуем без kl-параметра если он есть
                if isinstance(kwargs.get('data'), dict) and 'kl' in kwargs['data']:
                    data_copy = kwargs['data'].copy()
                    del data_copy['kl']
                    kwargs['data'] = data_copy
                    time.sleep(1)
                    continue
                    
            resp.raise_for_status()
            
            # Восстанавливаем заголовки если меняли для DDG
            if "duckduckgo.com" in url:
                session.headers.update(existing_headers)
                
            return resp
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            last_exc = e
            retries += 1
            if retries <= MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_FACTOR ** retries)
                continue
            
            # Восстанавливаем заголовки если меняли для DDG
            if "duckduckgo.com" in url:
                session.headers.update(existing_headers)
                
            raise last_exc
    
    # Восстанавливаем заголовки если меняли для DDG
    if "duckduckgo.com" in url:
        session.headers.update(existing_headers)
        
    raise last_exc or Exception("Unknown error")