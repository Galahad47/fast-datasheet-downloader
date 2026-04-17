# searcher.py

import concurrent.futures
from pathlib import Path
from urllib.parse import urljoin
from typing import List, Tuple, Optional, Callable
from llm_searcher import LLMDatasheetSearcher
import requests
from bs4 import BeautifulSoup

import config
from utils import (
    sanitize_filename,
    is_pdf_by_head,
    looks_like_pdf_url,
    unwrap_ddg_redirect,
    request_with_retry,
)



class DatasheetDownloader:
    def __init__(self, out_dir: Path, log_callback=None):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log = log_callback or (lambda msg: None)
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.llm_searcher = LLMDatasheetSearcher(log_callback=self.log)
    # --------------------------------------------------------
    # 1. Поиск через DuckDuckGo
    # --------------------------------------------------------
    def search_duckduckgo(self, query: str, max_results: int = 10) -> List[Tuple[str, str]]:
        """Возвращает список (title, url) из HTML-выдачи DuckDuckGo."""
        data = {"q": query, "kl": "ru-ru"}
        try:
            r = request_with_retry(self.session, "POST", config.SEARCH_URL_DDG, data=data)
        except Exception as e:
            self.log(f"  DDG ошибка: {e}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            title = a.get_text(" ", strip=True)
            if href:
                results.append((title, href))
            if len(results) >= max_results:
                break
        return results

    # --------------------------------------------------------
    # 2. Прямой поиск на alldatasheet.com
    # --------------------------------------------------------
    def search_alldatasheet(self, part_name: str) -> List[str]:
        """Ищет на alldatasheet.com, возвращает прямые ссылки на PDF."""
        try:
            params = {"SearchWord": part_name}
            r = request_with_retry(self.session, "GET", config.SEARCH_URL_ALLDATASHEET, params=params)
        except Exception as e:
            self.log(f"  Alldatasheet ошибка: {e}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        pdf_links = []
        for a in soup.select("a[href*='view_download.php']"):
            href = urljoin(r.url, a['href'])
            if self._check_pdf_link(href):
                pdf_links.append(href)
        return pdf_links

    # --------------------------------------------------------
    # 3. Прямой поиск на datasheetspdf.com
    # --------------------------------------------------------
    def search_datasheetspdf(self, part_name: str) -> List[str]:
        """Ищет на datasheetspdf.com, возвращает прямые PDF ссылки."""
        try:
            params = {"s": part_name}
            r = request_with_retry(self.session, "GET", config.SEARCH_URL_DATASHEETSPDF, params=params)
        except Exception as e:
            self.log(f"  Datasheetspdf ошибка: {e}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        pdf_links = []
        for a in soup.find_all("a", href=True):
            href = a['href'].lower()
            if "download" in href or href.endswith(".pdf"):
                full = urljoin(r.url, a['href'])
                if self._check_pdf_link(full):
                    pdf_links.append(full)
        return pdf_links

    def _check_pdf_link(self, url: str) -> bool:
        """Проверяет, что URL ведёт к PDF (HEAD-запросом)."""
        return is_pdf_by_head(url, self.session)

    # --------------------------------------------------------
    # 4. Параллельный поиск по источникам
    # --------------------------------------------------------
    
    def search_sources_parallel(self, part_name: str) -> Optional[str]:
        """
        Параллельно запускает поиск по всем источникам.
        Возвращает первый найденный прямой URL на PDF или None.
        """
        sources = [
            ('DDG', lambda: self._search_ddg_wrapper(part_name)),
            ('Alldatasheet', lambda: self.search_alldatasheet(part_name)),
            ('Datasheetspdf', lambda: self.search_datasheetspdf(part_name))
        ]
        if self.llm_searcher.is_available():
            sources.append(('DeepSeek', lambda: self._search_llm_wrapper(part_name)))

        def search_source(name: str, func: Callable[[], List[str]]) -> Optional[str]:
            try:
                urls = func()
                for url in urls:
                    if self._check_pdf_link(url):
                        self.log(f"  найдено через {name}: {url}")
                        return url
                return None
            except Exception as e:
                self.log(f"  ошибка источника {name}: {e}")
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as executor:
            future_to_source = {
                executor.submit(search_source, name, func): name
                for name, func in sources
            }
            for future in concurrent.futures.as_completed(future_to_source):
                result = future.result()
                if result:
                    # Отменяем остальные задачи
                    for f in future_to_source:
                        f.cancel()
                    return result
        return None

    def _search_ddg_wrapper(self, part_name: str) -> List[str]:
        query = f"{part_name} datasheet pdf"
        results = self.search_duckduckgo(query, max_results=5)
        return [unwrap_ddg_redirect(url) for _, url in results]

    # --------------------------------------------------------
    # 5. Сбор кандидатов (fallback, если прямые ссылки не найдены)
    # --------------------------------------------------------
    def find_candidates(self, part_name: str) -> List[Tuple[int, str]]:
        """Возвращает отсортированный список (score, url) потенциальных PDF."""
        candidates = []

        # DuckDuckGo
        query = f"{part_name} datasheet pdf"
        ddg_results = self.search_duckduckgo(query, max_results=8)
        for title, raw_url in ddg_results:
            url = unwrap_ddg_redirect(raw_url)
            score = self._score_url(url, title, part_name)
            candidates.append((score, url))

        # Alldatasheet
        for url in self.search_alldatasheet(part_name):
            score = self._score_url(url, "", part_name) + 10
            candidates.append((score, url))

        # Datasheetspdf
        for url in self.search_datasheetspdf(part_name):
            score = self._score_url(url, "", part_name) + 8
            candidates.append((score, url))

        # Удаление дубликатов
        seen = set()
        unique = []
        for score, url in sorted(candidates, key=lambda x: x[0], reverse=True):
            if url not in seen:
                seen.add(url)
                unique.append((score, url))
        return unique

    def _score_url(self, url: str, title: str, part_name: str) -> int:
        """Оценивает релевантность URL и заголовка."""
        score = 0
        text = f"{title} {url}".lower()
        part_lower = part_name.lower()

        if "datasheet" in text:
            score += 5
        if "pdf" in text or url.lower().endswith(".pdf"):
            score += 5

        trusted_domains = [
            "alldatasheet.com", "datasheetspdf.com", "pdf.datasheetcatalog.com",
            "datasheetarchive.com", "datasheet39.com", "datasheet4u.com",""
        ]
        for domain in trusted_domains:
            if domain in url:
                score += 10
                break

        if part_lower in text:
            score += 3

        if looks_like_pdf_url(url):
            score += 7

        return score

    # --------------------------------------------------------
    # 6. Извлечение PDF-ссылок с веб-страницы
    # --------------------------------------------------------
    def find_pdf_links_on_page(self, page_url: str) -> List[str]:
        """Парсит страницу в поисках ссылок на PDF (включая iframe)."""
        try:
            r = request_with_retry(self.session, "GET", page_url)
        except Exception:
            return []

        ctype = r.headers.get("Content-Type", "").lower()
        if "application/pdf" in ctype:
            return [r.url]

        soup = BeautifulSoup(r.text, "html.parser")
        pdf_links = []

        for a in soup.find_all("a", href=True):
            full = urljoin(r.url, a["href"])
            if looks_like_pdf_url(full) or self._check_pdf_link(full):
                pdf_links.append(full)

        for tag in soup.find_all(["iframe", "embed"], src=True):
            full = urljoin(r.url, tag["src"])
            if looks_like_pdf_url(full) or self._check_pdf_link(full):
                pdf_links.append(full)

        return pdf_links

    # --------------------------------------------------------
    # 7. Скачивание файла
    # --------------------------------------------------------
    def download_file(self, url: str, out_path: Path) -> bool:
        """Скачивает файл по URL, проверяя Content-Type."""
        try:
            with request_with_retry(self.session, "GET", url, stream=True) as r:
                ctype = r.headers.get("Content-Type", "").lower()
                if "pdf" not in ctype and not looks_like_pdf_url(r.url):
                    raise ValueError(f"Не PDF: {r.url} ({ctype})")

                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return True
        except Exception as e:
            self.log(f"  ошибка скачивания: {e}")
            return False

    # --------------------------------------------------------
    # 8. Главный метод поиска и загрузки
    # --------------------------------------------------------
    def find_and_download_datasheet(self, part_name: str) -> bool:
        """Основной рабочий процесс для одного наименования."""
        self.log(f"Поиск: {part_name}")

        # 1. Параллельный поиск прямых PDF-ссылок
        direct_pdf = self.search_sources_parallel(part_name)
        if direct_pdf:
            out_path = self.out_dir / f"{sanitize_filename(part_name)}.pdf"
            if self.download_file(direct_pdf, out_path):
                self.log(f"  OK: {out_path.name}")
                return True

        # 2. Fallback: сбор кандидатов и обход страниц
        candidates = self.find_candidates(part_name)
        if not candidates:
            self.log("  кандидатов не найдено")
            return False

        for score, url in candidates[:5]:  # ограничим 5 лучшими
            self.log(f"  проверка: {url} (score={score})")
            try:
                if looks_like_pdf_url(url):
                    out_path = self.out_dir / f"{sanitize_filename(part_name)}.pdf"
                    if self.download_file(url, out_path):
                        self.log(f"  OK: {out_path.name}")
                        return True
                    continue

                pdf_links = self.find_pdf_links_on_page(url)
                for pdf_url in pdf_links:
                    out_path = self.out_dir / f"{sanitize_filename(part_name)}.pdf"
                    if self.download_file(pdf_url, out_path):
                        self.log(f"  OK: {out_path.name}")
                        return True
            except Exception as e:
                self.log(f"  ошибка обработки {url}: {e}")
                continue
        if config.USE_LLM_AS_FALLBACK and self.llm_searcher_available():
            self.log(' Применение LLM для следующего наименования:',part_name)
            llm_url = self.llm_searcher.search_pdf_url(part_name)
            if llm_url:
                out_path = self.out_dir / f"{sanitize_filename(part_name)}.pdf"
                if self.download_file(llm_url,out_path):
                    self.log(f"OK (LLM):{out_path.name}")
                    return True
        self.log("  не найдено подходящего PDF")
        return False
    
    def _search_llm_wrapper(self, part_name: str) -> List[str]:
        """Обёртка для LLM-поиска, возвращает список из одного URL или пустой список."""
        url = self.llm_searcher.search_pdf_url(part_name)
        return [url] if url else []