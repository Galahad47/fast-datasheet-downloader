# config.py
import os

# =============================================================================
# URLs для поисковых систем
# =============================================================================
SEARCH_URL_DDG = "https://html.duckduckgo.com/html/"
SEARCH_URL_ALLDATASHEET = "https://www.alldatasheet.com/view.jsp"
SEARCH_URL_DATASHEETSPDF = "https://datasheetspdf.com/search"

# Заголовки HTTP для маскировки под браузер
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# =============================================================================
# Параметры сетевых запросов
# =============================================================================
REQUEST_TIMEOUT = 25
MAX_RETRIES = 2
RETRY_BACKOFF_FACTOR = 1.5

# Параметры параллелизма
MAX_WORKERS_PER_SOURCE = 3   # одновременных запросов к одному источнику
MAX_WORKERS_TOTAL = 5        # одновременно обрабатываемых компонентов

# Дополнительные поисковые системы для обхода блокировок
FALLBACK_SEARCH_ENGINES = [
    "duckduckgo",
    "google_scholar",
    "bing",  # Добавлен как резервный источник
]

# =============================================================================
# LLM Configuration (DeepSeek API) - ОТКЛЮЧЕНО
# =============================================================================
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')  # Рекомендуется через переменную окружения
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
USE_LLM_AS_FALLBACK = False  # Отключено из-за проблем с блокировками
LLM_MAX_WORKERS = 2
LLM_REQUEST_TIMEOUT = 45  # Увеличен для сложных запросов

# =============================================================================
# Типы информации для поиска
# =============================================================================
INFO_TYPES = {
    "datasheet": {
        "name": "Даташит",
        "description": "Техническая документация компонента",
        "file_extension": ".pdf",
        "keywords": ["datasheet", "specification", "technical documentation"],
        "llm_prompt_template": "Найди прямую ссылку на PDF-файл даташита для компонента: {query}",
    },
    "application_note": {
        "name": "Приложение",
        "description": "Примеры применения и схемы",
        "file_extension": ".pdf",
        "keywords": ["application note", "example circuit", "reference design"],
        "llm_prompt_template": "Найди прямую ссылку на PDF-файл с примером применения для компонента: {query}",
    },
    "user_manual": {
        "name": "Руководство пользователя",
        "description": "Инструкции по использованию",
        "file_extension": ".pdf",
        "keywords": ["user manual", "guide", "instruction"],
        "llm_prompt_template": "Найди прямую ссылку на PDF-файл руководства пользователя для: {query}",
    },
    "whitepaper": {
        "name": "Технический документ",
        "description": "Исследования и аналитика",
        "file_extension": ".pdf",
        "keywords": ["whitepaper", "technical paper", "research"],
        "llm_prompt_template": "Найди прямую ссылку на PDF-файл технического документа по теме: {query}",
    },
    "review": {
        "name": "Обзор",
        "description": "Обзоры и сравнения",
        "file_extension": ".html",
        "keywords": ["review", "comparison", "benchmark"],
        "llm_prompt_template": "Найди URL страницы с подробным обзором или сравнением для: {query}",
    },
    "forum": {
        "name": "Форум",
        "description": "Обсуждения и вопросы",
        "file_extension": ".html",
        "keywords": ["forum", "discussion", "community"],
        "llm_prompt_template": "Найди URL страницы форума с обсуждением темы: {query}",
    },
    "news": {
        "name": "Новости",
        "description": "Последние новости и анонсы",
        "file_extension": ".html",
        "keywords": ["news", "announcement", "release"],
        "llm_prompt_template": "Найди URL страницы с последними новостями по теме: {query}",
    },
    "custom": {
        "name": "Пользовательский запрос",
        "description": "Свой собственный поисковый запрос",
        "file_extension": "",
        "keywords": [],
        "llm_prompt_template": "{query}",
    },
}

# Поисковые запросы по умолчанию для разных типов
DEFAULT_SEARCH_PATTERNS = {
    "datasheet": "{query} datasheet pdf",
    "application_note": "{query} application note pdf",
    "user_manual": "{query} user manual guide pdf",
    "whitepaper": "{query} whitepaper technical pdf",
    "review": "{query} review comparison",
    "forum": "{query} forum discussion",
    "news": "{query} news announcement",
    "custom": "{query}",
}

# Домены, которым доверяем для каждого типа
TRUSTED_DOMAINS = {
    "datasheet": [
        "alldatasheet.com", "pdf.datasheetcatalog.com",
        "datasheetarchive.com", "datasheet39.com", "datasheet4u.com",
        "ti.com", "analog.com", "st.com", "infineon.com", "nxp.com",
        "microchip.com", "renesas.com", "onsemi.com", " Vishay.com"
    ],
    "application_note": [
        "ti.com", "analog.com", "st.com", "infineon.com", "nxp.com",
        "microchip.com", "renesas.com", "allaboutcircuits.com"
    ],
    "user_manual": [
        "manualslib.com", "manualsonline.com", "elektroda.pl"
    ],
    "whitepaper": [
        "ieee.org", "sciencedirect.com", "researchgate.net", "arxiv.org"
    ],
    "review": [
        "tomshardware.com", "anandtech.com", "techpowerup.com", "habr.com"
    ],
    "forum": [
        "reddit.com", "stackexchange.com", "eevblog.com", "forum.arduino.cc",
        "habr.com", "radiokot.ru"
    ],
    "news": [
        "eetimes.com", "electronicdesign.com", "edn.com", "3dnews.ru"
    ],
}