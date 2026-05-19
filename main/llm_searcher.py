# llm_searcher.py
import os
import re
from typing import Optional, List


class LLMInfoSearcher:
    """Заглушка для LLM поисковика (LLM-функционал удалён)."""

    def __init__(self, log_callback=None, info_type: str = "datasheet"):
        self.log = log_callback or (lambda msg: None)
        self.info_type = info_type
        self.log("ℹ️ LLM-поиск отключён")

    def is_available(self) -> bool:
        """Всегда возвращает False, т.к. LLM отключён."""
        return False

    def search_url(self, query: str, custom_prompt: Optional[str] = None) -> Optional[str]:
        """Заглушка - всегда возвращает None."""
        return None

    def search_pdf_url(self, part_name: str) -> Optional[str]:
        """Обратная совместимость: всегда возвращает None."""
        return None


# Алиас для обратной совместимости
LLMDatasheetSearcher = LLMInfoSearcher