import hashlib
import logging
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

logger = logging.getLogger('scraper')


class BaseParser:
    """Базовый класс для всех парсеров торговых площадок."""

    marketplace_name = None
    marketplace_url = None

    REQUEST_TIMEOUT = 15
    REQUEST_DELAY = 1  # пауза между запросами страниц пагинации, сек
    MAX_PAGES = 3       # ограничение на количество страниц каталога за один запуск

    # Город, для которого собираются цены и наличие (см. settings.SCRAPE_CITY).
    # Каждый парсер сам решает, как передать его площадке — через cookie,
    # заголовок или параметр запроса (см. get_headers/get_cookies и т.п.).
    CITY = settings.SCRAPE_CITY

    # SOCKS5-прокси для чередования с прямым подключением (см. settings.SCRAPE_PROXY_URL,
    # настраивается через .env). Пустая строка — прокси не используется, все
    # запросы идут с прямого подключения.
    PROXY_URL = settings.SCRAPE_PROXY_URL

    # Раз в сколько страниц пагинации чередуется прямое подключение и прокси:
    # страницы 0..N-1 — прямое подключение, N..2N-1 — прокси, и так далее.
    PROXY_SWITCH_PAGES = 3

    def use_proxy(self, page: int) -> bool:
        """Решает, использовать ли прокси для страницы пагинации с номером page."""
        if not self.PROXY_URL:
            return False
        return (page // self.PROXY_SWITCH_PAGES) % 2 == 1

    def get_proxies(self, page: int) -> dict | None:
        """dict для requests(proxies=...) с учётом чередования прокси, либо
        None — для прямого подключения."""
        if not self.use_proxy(page):
            return None
        return {'http': self.PROXY_URL, 'https': self.PROXY_URL}

    def get_browser_proxy_arg(self, page: int) -> str | None:
        """Аргумент --proxy-server=... для запуска Chrome через zendriver
        с учётом чередования прокси, либо None — для прямого подключения.

        Логин/пароль (если есть в PROXY_URL) Chrome через --proxy-server не
        принимает — для них используется отдельная авторизация на уровне CDP
        (см. BaseParser.authenticate_proxy)."""
        if not self.use_proxy(page):
            return None
        parsed = urlparse(self.PROXY_URL)
        return f'--proxy-server=socks5://{parsed.hostname}:{parsed.port}'

    async def authenticate_proxy(self, browser):
        """Включает авторизацию прокси по логину/паролю из PROXY_URL для всех
        вкладок браузера zendriver (для SOCKS5-прокси, требующих логин/пароль)."""
        parsed = urlparse(self.PROXY_URL)
        if not (parsed.username and parsed.password):
            return

        from zendriver.cdp import fetch

        async def auth_handler(event: fetch.AuthRequired, tab):
            await tab.send(fetch.continue_with_auth(
                request_id=event.request_id,
                auth_challenge_response=fetch.AuthChallengeResponse(
                    response='ProvideCredentials',
                    username=parsed.username,
                    password=parsed.password,
                ),
            ))

        async def request_handler(event: fetch.RequestPaused, tab):
            await tab.send(fetch.continue_request(request_id=event.request_id))

        main_tab = browser.main_tab
        await main_tab.send(fetch.enable(handle_auth_requests=True))
        main_tab.add_handler(fetch.AuthRequired, auth_handler)
        main_tab.add_handler(fetch.RequestPaused, request_handler)

    def get_headers(self):
        return {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'
            ),
            'Accept-Language': 'ru-RU,ru;q=0.9',
        }

    def get_soup(self, url, **kwargs):
        """Выполняет GET-запрос и возвращает разобранную страницу."""
        response = requests.get(url, headers=self.get_headers(), timeout=self.REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'lxml')

    def get_json(self, url, **kwargs):
        """Выполняет GET-запрос и возвращает JSON-ответ."""
        response = requests.get(url, headers=self.get_headers(), timeout=self.REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json()

    def post_json(self, url, payload, headers=None, **kwargs):
        """Выполняет POST-запрос с JSON-телом и возвращает JSON-ответ."""
        merged_headers = self.get_headers()
        if headers:
            merged_headers.update(headers)
        response = requests.post(url, json=payload, headers=merged_headers, timeout=self.REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json()

    def sleep(self):
        """Задержка между запросами страниц пагинации, чтобы не нагружать сайт."""
        time.sleep(self.REQUEST_DELAY)

    def parse(self) -> list[dict]:
        """Возвращает список словарей с ключами:
        external_id, name, brand, capacity_gb, memory_type, frequency_mhz, url, price
        """
        raise NotImplementedError

    @staticmethod
    def parse_price(text):
        """Извлекает число из строки с ценой, например '12 990 ₽' -> 12990.0.

        Берёт только первую группу цифр (с разделителями-пробелами) —
        если в тексте случайно склеились два числа (например, цена и
        сумма бонусов без разделителя), это не даёт им объединиться
        в одно огромное число.
        """
        if not text:
            return None
        match = re.search(r'\d[\d\s]*\d|\d', text)
        if not match:
            return None
        digits = re.sub(r'\s', '', match.group(0))
        return float(digits) if digits else None

    @staticmethod
    def extract_external_id(url: str) -> str:
        """Извлекает числовой ID товара из ссылки, иначе хэширует ссылку."""
        # ID как отдельный сегмент пути: /product/12345/
        match = re.search(r'/(\d{4,})(?:[/?#]|$)', url)
        if match:
            return match.group(1)
        # ID на конце slug-а через дефис: .../product-name-12345/
        match = re.search(r'-(\d{4,})/?(?:[?#]|$)', url)
        if match:
            return match.group(1)
        return hashlib.md5(url.encode('utf-8')).hexdigest()[:16]

    # Римские цифры в обозначении типа памяти (например, "DDR-III", "DDR II")
    # встречаются у некоторых производителей вместо привычного "DDR3"/"DDR2".
    MEMORY_TYPE_ROMAN = {'II': '2', 'III': '3', 'IV': '4', 'V': '5'}

    @classmethod
    def parse_ram_specs(cls, name: str) -> dict:
        """Извлекает объём (ГБ), тип памяти (DDR2-DDR5) и частоту (МГц) из названия товара."""
        specs: dict[str, int | str | None] = {
            'capacity_gb': None, 'memory_type': None, 'frequency_mhz': None,
        }

        memory_type_match = re.search(r'DDR([2-5])L?', name, re.IGNORECASE)
        if memory_type_match:
            specs['memory_type'] = 'DDR' + memory_type_match.group(1)
        else:
            roman_match = re.search(r'DDR[\s\-]?(I{2,3}|IV|V)\b', name, re.IGNORECASE)
            if roman_match:
                specs['memory_type'] = 'DDR' + cls.MEMORY_TYPE_ROMAN[roman_match.group(1).upper()]

        capacity_match = re.search(r'(\d+)\s*(?:GB|ГБ|Гб)', name, re.IGNORECASE)
        if capacity_match:
            specs['capacity_gb'] = int(capacity_match.group(1))

        frequency_match = re.search(r'(\d{3,5})\s*(?:MHz|МГц|Mhz)', name, re.IGNORECASE)
        if frequency_match:
            specs['frequency_mhz'] = int(frequency_match.group(1))

        return specs

    PART_NUMBER_RE = re.compile(r'[A-Z0-9][A-Z0-9\-/]{5,}[A-Z0-9]', re.IGNORECASE)
    PART_NUMBER_STOP_RE = re.compile(
        r'^(?:DDR[2345][A-Z]{0,2}(?:-?\d{3,5})?|\d+GB|\d{3,5}(?:MHZ|MGH)?)$',
        re.IGNORECASE,
    )

    @classmethod
    def extract_part_number(cls, name: str) -> str | None:
        """Извлекает артикул производителя из названия товара.

        Ищет буквенно-цифровые токены вида KF432C16RB12K2/32,
        AX5U6000C3016G-DTLABBK и т.п. Токены, похожие на спецификацию
        (DDR4, DDR5-5200, 3200MHz, 16GB), отбрасываются. Из оставшихся
        кандидатов берётся самый длинный — артикулы длиннее случайных
        совпадений вроде "2x16GB".
        """
        candidates = []
        for token in cls.PART_NUMBER_RE.findall(name):
            if cls.PART_NUMBER_STOP_RE.match(token):
                continue
            if not (re.search(r'[A-Za-z]', token) and re.search(r'\d', token)):
                continue
            candidates.append(token)

        if not candidates:
            return None
        return max(candidates, key=len).upper()

    # Элемент списка — либо строка (бренд ищется и возвращается как есть),
    # либо пара (искомое название, каноническое название бренда) — для
    # суб-брендов и альтернативных написаний (например, XPG -> ADATA).
    KNOWN_BRANDS = [
        'Kingston', 'Crucial', 'ADATA', ('A-Data', 'ADATA'), ('XPG', 'ADATA'),
        'Patriot', 'GoodRAM', 'Samsung',
        'Hynix', 'Apacer', 'AMD', 'Corsair', 'G.Skill', 'TeamGroup', 'Team',
        'Digma', 'Foxline', 'Netac', 'Silicon Power', 'Transcend',
        'KingSpec', 'Indilinx', 'AGI', 'ТМИ', 'BaseTech', 'Tesla', 'Qumo',
        'Advantech', 'CBR', 'Innodisk', 'KingFast', 'Hixa', 'ExeGate', 'HPE',
        'Micron', 'xFusion', 'DEXP', 'ARDOR GAMING', 'Acer', 'GeIL', 'Asgard',
        'OCPC', 'Neo Forza', 'KingDian',
    ]

    # Общие слова, с которых часто начинается название товара и которые
    # сами по себе не являются брендом (например, "Оперативная память
    # NewBrand DDR5..." — пропускаем первые два слова и берём "NewBrand").
    BRAND_FALLBACK_STOPWORDS = {'оперативная', 'память', 'memory', 'озу', 'модуль', 'ram'}

    @classmethod
    def guess_brand(cls, name: str) -> str:
        """Определяет бренд модуля памяти, ища известные бренды по всему названию товара."""
        for entry in cls.KNOWN_BRANDS:
            pattern, canonical = entry if isinstance(entry, tuple) else (entry, entry)
            if re.search(rf'\b{re.escape(pattern)}\b', name, re.IGNORECASE):
                return canonical
        for word in name.split():
            if word.lower() not in cls.BRAND_FALLBACK_STOPWORDS:
                return word
        return 'Unknown'
