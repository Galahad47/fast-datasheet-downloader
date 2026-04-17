# llm_searcher.py
import os
from typing import Optional
from openai import OpenAI

import config


class LLMDatasheetSearcher:

    SYSTEM_PROMPT = """
Ты — продвинутый поисковый ассистент, специализирующийся на поиске технической документации.
Твоя задача — найти актуальную прямую ссылку на PDF-файл даташита для заданного электронного компонента.

**Порядок действий:**
1. Проанализируй запрос пользователя с названием компонента.
2. Сформулируй поисковый запрос, чтобы найти страницу с даташитом на официальном сайте производителя.
3. Найди на странице прямую ссылку на PDF-файл.
4. Верни только полный URL этого PDF-файла.

**Критически важно:**
- Ищи информацию на официальных сайтах производителей.
- Игнорируй сайты-агрегаторы (alldatasheet.com, datasheetspdf.com, datasheetcatalog.com и подобные).
- Твой ответ должен содержать только URL, начинающийся с http:// или https:// и заканчивающийся на .pdf.
- Если найти даташит не удалось, верни ровно "NOT_FOUND".
- Не добавляй пояснений, комментариев или форматирования.
"""

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda msg: None)

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

    def search_pdf_url(self, part_name: str) -> Optional[str]:
        """
        Отправляет запрос к DeepSeek и возвращает URL PDF или None.
        """
        if not self.is_available():
            return None

        self.log(f"  🤖 LLM поиск для: {part_name}")

        try:
            response = self.client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Найди даташит в формате PDF для компонента: {part_name}"}
                ],
                temperature=0.1,           # Низкая температура для более детерминированного ответа
                max_tokens=256,            # URL обычно короткий
                timeout=config.LLM_REQUEST_TIMEOUT,
                stream=False
            )

            result = response.choices[0].message.content.strip()

            # Базовая валидация ответа
            if result == "NOT_FOUND" or not result:
                self.log(f"  🤖 LLM не нашёл даташит")
                return None

            # Проверяем, что ответ похож на URL
            if result.startswith(("http://", "https://")) and ".pdf" in result.lower():
                self.log(f"  🤖 LLM нашёл: {result}")
                return result
            else:
                self.log(f"  🤖 LLM вернул невалидный URL: {result[:100]}...")
                return None

        except Exception as e:
            self.log(f"  🤖 LLM ошибка: {e}")
            return None