# llm_searcher.py
import os
import re
from typing import Optional, List
from openai import OpenAI

import config


class LLMInfoSearcher:
    """Универсальный поисковик информации через LLM с поддержкой различных типов контента."""

    BASE_SYSTEM_PROMPT = """
Ты — продвинутый поисковый ассистент, специализирующийся на поиске технической документации и информации.
Твоя задача — найти актуальную прямую ссылку на файл или веб-страницу по запросу пользователя.

**Порядок действий:**
1. Проанализируй запрос пользователя и определи тип требуемой информации.
2. Сформулируй поисковый запрос для нахождения релевантного ресурса.
3. Найди прямую ссылку на файл (PDF, HTML) или страницу с информацией.
4. Верни только полный URL найденного ресурса.

**Критически важно:**
- Приоритет отдавай официальным источникам и авторитетным сайтам.
- Для документов предпочитай прямые ссылки на файлы (PDF, DOCX и т.д.).
- Твой ответ должен содержать только URL, начинающийся с http:// или https://.
- Если найти информацию не удалось, верни ровно "NOT_FOUND".
- Не добавляй пояснений, комментариев или форматирования.
"""

    TYPE_SPECIFIC_INSTRUCTIONS = {
        "datasheet": "Ищи PDF-файлы даташитов на официальных сайтах производителей электроники. Избегай агрегаторов.",
        "application_note": "Ищи PDF-файлы с примерами применения, схемами и рекомендациями от производителей.",
        "user_manual": "Ищи руководства пользователя и инструкции в формате PDF.",
        "whitepaper": "Ищи технические документы, исследования и аналитику в формате PDF от авторитетных источников.",
        "review": "Ищи подробные обзоры и сравнения на технических сайтах и в блогах.",
        "forum": "Ищи обсуждения на профильных форумах и сообществах (Reddit, StackExchange, специализированные форумы).",
        "news": "Ищи последние новости и анонсы на новостных порталах и официальных сайтах.",
        "custom": "Выполни поиск по точному запросу пользователя, находя наиболее релевантные ресурсы.",
    }

    def __init__(self, log_callback=None, info_type: str = "datasheet"):
        self.log = log_callback or (lambda msg: None)
        self.info_type = info_type if info_type in config.INFO_TYPES else "datasheet"

        if not config.DEEPSEEK_API_KEY:
            self.log("⚠️ DeepSeek API ключ не найден. LLM-поиск отключён.")
            self.client = None
            return

        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

    def is_available(self) -> bool:
        """Проверяет, готов ли клиент к работе."""
        return self.client is not None

    def _build_system_prompt(self) -> str:
        """Формирует системный промпт с учётом типа информации."""
        type_instruction = self.TYPE_SPECIFIC_INSTRUCTIONS.get(self.info_type, "")
        type_info = config.INFO_TYPES.get(self.info_type, {})
        file_ext = type_info.get("file_extension", "")
        
        prompt = self.BASE_SYSTEM_PROMPT
        
        if type_instruction:
            type_name = type_info.get("name", self.info_type)
            prompt += f'\n\n**Специфика для типа "{type_name}":**\n{type_instruction}'
        
        if file_ext == ".pdf":
            prompt += "\n- Предпочитай прямые ссылки на PDF-файлы."
        elif file_ext == ".html":
            prompt += "\n- Подходят ссылки на веб-страницы (HTML)."
        
        return prompt

    def search_url(self, query: str, custom_prompt: Optional[str] = None) -> Optional[str]:
        """
        Универсальный метод поиска URL по запросу.
        
        Args:
            query: Поисковый запрос
            custom_prompt: Пользовательский промпт (переопределяет шаблонный)
            
        Returns:
            URL найденного ресурса или None
        """
        if not self.is_available():
            return None

        self.log(f"  🤖 LLM поиск [{config.INFO_TYPES.get(self.info_type, {}).get('name', self.info_type)}]: {query}")

        # Формируем пользовательский промпт
        if custom_prompt:
            user_prompt = custom_prompt.format(query=query)
        else:
            template = config.INFO_TYPES.get(self.info_type, {}).get("llm_prompt_template", "{query}")
            user_prompt = template.format(query=query)

        try:
            response = self.client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=512,
                timeout=config.LLM_REQUEST_TIMEOUT,
                stream=False
            )

            result = response.choices[0].message.content.strip()

            # Базовая валидация ответа
            if result == "NOT_FOUND" or not result:
                self.log(f"  🤖 LLM не нашёл информацию")
                return None

            # Извлекаем URL из ответа (на случай если LLM добавил лишнее)
            url_match = re.search(r'https?://[^\s<>\"{}|\\^`\[\]]+', result)
            if url_match:
                url = url_match.group(0)
                # Убираем возможные хвосты
                url = re.sub(r'[.,;:!?]+$', '', url)
                self.log(f"  🤖 LLM нашёл: {url}")
                return url
            else:
                self.log(f"  🤖 LLM вернул невалидный ответ: {result[:100]}...")
                return None

        except Exception as e:
            self.log(f"  🤖 LLM ошибка: {e}")
            return None

    def search_pdf_url(self, part_name: str) -> Optional[str]:
        """Обратная совместимость: поиск PDF (для datasheet)."""
        return self.search_url(part_name)


# Алиас для обратной совместимости
LLMDatasheetSearcher = LLMInfoSearcher