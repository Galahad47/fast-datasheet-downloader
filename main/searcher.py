# searcher.py

import concurrent.futures
from pathlib import Path
from urllib.parse import urljoin
from typing import List, Tuple, Optional, Callable, Dict
from llm_searcher import LLMInfoSearcher
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


class InfoSearcher:
    """Универсальный поисковик информации с поддержкой различных типов контента."""
    
    def __init__(self, out_dir: Path, log_callback=None, info_type: str = "datasheet"):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log = log_callback or (lambda msg: None)
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        self.info_type = info_type if info_type in config.INFO_TYPES else "datasheet"
        self.llm_searcher = LLMInfoSearcher(log_callback=self.log, info_type=self.info_type)
        
        # Получаем настройки для текущего типа информации
        self.type_config = config.INFO_TYPES.get(self.info_type, {})
        self.file_extension = self.type_config.get("file_extension", "")
        self.search_pattern = config.DEFAULT_SEARCH_PATTERNS.get(self.info_type, "{query}")
        self.trusted_domains = config.TRUSTED_DOMAINS.get(self.info_type, [])
    
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
    # 2. Прямой поиск на alldatasheet.com (только для datasheet)
    # --------------------------------------------------------
    def search_alldatasheet(self, part_name: str) -> List[str]:
        """Ищет на alldatasheet.com, возвращает прямые ссылки на PDF."""
        if self.info_type != "datasheet":
            return []
            
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
    # 3. Прямой поиск на datasheetspdf.com (только для datasheet)
    # --------------------------------------------------------
    def search_datasheetspdf(self, part_name: str) -> List[str]:
        """Ищет на datasheetspdf.com, возвращает прямые PDF ссылки."""
        if self.info_type != "datasheet":
            return []
            
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
    
    def search_sources_parallel(self, query: str) -> Optional[str]:
        """
        Параллельно запускает поиск по всем источникам.
        Возвращает первый найденный прямой URL или None.
        """
        sources = [
            ('DDG', lambda: self._search_ddg_wrapper(query)),
        ]
        
        # Добавляем специализированные источники только для datasheet
        if self.info_type == "datasheet":
            sources.extend([
                ('Alldatasheet', lambda: self.search_alldatasheet(query)),
                ('Datasheetspdf', lambda: self.search_datasheetspdf(query))
            ])
        
        if self.llm_searcher.is_available():
            sources.append(('LLM', lambda: self._search_llm_wrapper(query)))

        def search_source(name: str, func: Callable[[], List[str]]) -> Optional[str]:
            try:
                urls = func()
                for url in urls:
                    if self._check_content_type(url):
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

    def _search_ddg_wrapper(self, query: str) -> List[str]:
        search_query = self.search_pattern.format(query=query)
        results = self.search_duckduckgo(search_query, max_results=5)
        return [unwrap_ddg_redirect(url) for _, url in results]

    def _check_content_type(self, url: str) -> bool:
        """Проверяет соответствие типа контента ожидаемому."""
        if self.file_extension == ".pdf":
            return is_pdf_by_head(url, self.session)
        else:
            # Для HTML и других типов просто проверяем доступность
            try:
                r = self.session.head(url, timeout=10, allow_redirects=True)
                return r.status_code == 200
            except:
                return False

    # --------------------------------------------------------
    # 5. Сбор кандидатов (fallback, если прямые ссылки не найдены)
    # --------------------------------------------------------
    def find_candidates(self, query: str) -> List[Tuple[int, str]]:
        """Возвращает отсортированный список (score, url) потенциальных ресурсов."""
        candidates = []

        # DuckDuckGo
        search_query = self.search_pattern.format(query=query)
        ddg_results = self.search_duckduckgo(search_query, max_results=8)
        for title, raw_url in ddg_results:
            url = unwrap_ddg_redirect(raw_url)
            score = self._score_url(url, title, query)
            candidates.append((score, url))

        # Alldatasheet (только datasheet)
        if self.info_type == "datasheet":
            for url in self.search_alldatasheet(query):
                score = self._score_url(url, "", query) + 10
                candidates.append((score, url))

        # Datasheetspdf (только datasheet)
        if self.info_type == "datasheet":
            for url in self.search_datasheetspdf(query):
                score = self._score_url(url, "", query) + 8
                candidates.append((score, url))

        # Удаление дубликатов
        seen = set()
        unique = []
        for score, url in sorted(candidates, key=lambda x: x[0], reverse=True):
            if url not in seen:
                seen.add(url)
                unique.append((score, url))
        return unique

    def _score_url(self, url: str, title: str, query: str) -> int:
        """Оценивает релевантность URL и заголовка."""
        score = 0
        text = f"{title} {url}".lower()
        query_lower = query.lower()

        # Ключевые слова для типа информации
        keywords = self.type_config.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text:
                score += 5

        if "pdf" in text or url.lower().endswith(".pdf"):
            score += 5

        # Доверенные домены
        for domain in self.trusted_domains:
            if domain in url:
                score += 10
                break

        if query_lower in text:
            score += 3

        if looks_like_pdf_url(url):
            score += 7

        return score

    # --------------------------------------------------------
    # 6. Извлечение ссылок с веб-страницы
    # --------------------------------------------------------
    def find_links_on_page(self, page_url: str) -> List[str]:
        """Парсит страницу в поисках ссылок на файлы (включая iframe)."""
        try:
            r = request_with_retry(self.session, "GET", page_url)
        except Exception:
            return []

        ctype = r.headers.get("Content-Type", "").lower()
        if self.file_extension == ".pdf" and "application/pdf" in ctype:
            return [r.url]

        soup = BeautifulSoup(r.text, "html.parser")
        links = []

        for a in soup.find_all("a", href=True):
            full = urljoin(r.url, a["href"])
            if self._is_relevant_link(full):
                links.append(full)

        for tag in soup.find_all(["iframe", "embed"], src=True):
            full = urljoin(r.url, tag["src"])
            if self._is_relevant_link(full):
                links.append(full)

        return links

    def _is_relevant_link(self, url: str) -> bool:
        """Проверяет, соответствует ли ссылка типу искомого контента."""
        if self.file_extension == ".pdf":
            return looks_like_pdf_url(url) or self._check_pdf_link(url)
        else:
            # Для HTML принимаем любые ссылки на тот же домен или известные ресурсы
            return True

    # --------------------------------------------------------
    # 7. Скачивание файла
    # --------------------------------------------------------
    def download_file(self, url: str, out_path: Path) -> bool:
        """Скачивает файл по URL, проверяя Content-Type."""
        try:
            with request_with_retry(self.session, "GET", url, stream=True) as r:
                ctype = r.headers.get("Content-Type", "").lower()
                
                # Проверка типа контента
                if self.file_extension == ".pdf":
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
    def find_and_download(self, query: str) -> bool:
        """Основной рабочий процесс для одного запроса."""
        self.log(f"Поиск [{self.type_config.get('name', self.info_type)}]: {query}")

        # 1. Параллельный поиск прямых ссылок
        direct_url = self.search_sources_parallel(query)
        if direct_url:
            filename = sanitize_filename(query)
            ext = self.file_extension if self.file_extension else ".html"
            out_path = self.out_dir / f"{filename}{ext}"
            if self.download_file(direct_url, out_path):
                self.log(f"  OK: {out_path.name}")
                return True

        # 2. Fallback: сбор кандидатов и обход страниц
        candidates = self.find_candidates(query)
        if not candidates:
            self.log("  кандидатов не найдено")
            return False

        for score, url in candidates[:5]:  # ограничим 5 лучшими
            self.log(f"  проверка: {url} (score={score})")
            try:
                if looks_like_pdf_url(url) and self.file_extension == ".pdf":
                    filename = sanitize_filename(query)
                    out_path = self.out_dir / f"{filename}.pdf"
                    if self.download_file(url, out_path):
                        self.log(f"  OK: {out_path.name}")
                        return True
                    continue

                links = self.find_links_on_page(url)
                for link_url in links:
                    filename = sanitize_filename(query)
                    ext = self.file_extension if self.file_extension else ".html"
                    out_path = self.out_dir / f"{filename}{ext}"
                    if self.download_file(link_url, out_path):
                        self.log(f"  OK: {out_path.name}")
                        return True
            except Exception as e:
                self.log(f"  ошибка обработки {url}: {e}")
                continue
        
        # 3. LLM fallback
        if config.USE_LLM_AS_FALLBACK and self.llm_searcher.is_available():
            self.log(f'Применение LLM для: {query}')
            llm_url = self.llm_searcher.search_url(query)
            if llm_url:
                filename = sanitize_filename(query)
                ext = self.file_extension if self.file_extension else ".html"
                out_path = self.out_dir / f"{filename}{ext}"
                if self.download_file(llm_url, out_path):
                    self.log(f"OK (LLM):{out_path.name}")
                    return True
                    
        self.log("  не найдено подходящего ресурса")
        return False
    
    def _search_llm_wrapper(self, query: str) -> List[str]:
        """Обёртка для LLM-поиска, возвращает список из одного URL или пустой список."""
        url = self.llm_searcher.search_url(query)
        return [url] if url else []


# Алиас для обратной совместимости
DatasheetDownloader = InfoSearcher