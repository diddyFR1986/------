import logging
import re

import requests

from .base import BaseParser

logger = logging.getLogger('scraper')


class CitilinkParser(BaseParser):
    """Парсер каталога ОЗУ магазина Citilink (citilink.ru).

    Каталог отрисовывается на клиенте (Next.js SPA с виртуализацией списка),
    поэтому товары запрашиваются напрямую из GraphQL API, которое использует
    сам сайт для подгрузки карточек каталога.
    """

    marketplace_name = 'Citilink'
    marketplace_url = 'https://www.citilink.ru/'

    GRAPHQL_URL = 'https://www.citilink.ru/graphql/'
    CATEGORY_SLUG = 'moduli-pamyati'
    PER_PAGE = 36

    # id города Екатеринбурга в справочнике Citilink (см. settings.SCRAPE_CITY),
    # найден через GraphQL-запрос cities(input: {name: "Екатеринбург"}).
    CITY_ID = 'ekat_cl'

    # Безопасный предел страниц каталога (реально их ~10 при PER_PAGE=36 и ~330 товарах).
    MAX_PAGES = 15

    # Антибот QRATOR может выдавать пазл несколько раз подряд для одного
    # и того же запроса — даём несколько попыток решить его.
    MAX_CHALLENGE_ATTEMPTS = 5

    QUERY = '''
    query GetProducts($filter: CatalogFilter_ProductsFilterInput!) {
      productsFilter(filter: $filter) {
        record {
          products {
            id
            name
            slug
            price {
              current
            }
            images
          }
          pageInfo {
            page
            totalPages
          }
        }
      }
    }
    '''

    # Запасной запрос без поля images — на случай, если оно отсутствует
    # в схеме GraphQL (используется при ошибке валидации запроса).
    QUERY_NO_IMAGES = '''
    query GetProducts($filter: CatalogFilter_ProductsFilterInput!) {
      productsFilter(filter: $filter) {
        record {
          products {
            id
            name
            slug
            price {
              current
            }
          }
          pageInfo {
            page
            totalPages
          }
        }
      }
    }
    '''

    # Разбор JS-пазла антибота QRATOR (страница "Загрузка..." с кодом 429):
    # страница тайлит 1024-байтовый массив phrase на ~512 МБ, модифицирует
    # несколько байт в каждом тайле, считает число байт == -127 и обрезает
    # склеенную из кусочков строку на число символов, равное последней
    # ненулевой цифре этой суммы — результат кладётся в куку (см. _solve_qrator_challenge).
    _CHALLENGE_SEGMENT_RE = re.compile(
        r"var value2 = '([^']*)';\s*(value2 = value2\.split\(\"\"\)\.reverse\(\)\.join\(\"\"\)\s*)?"
        r"\s*value = value \+ value2;",
        re.S,
    )
    _CHALLENGE_PHRASE_RE = re.compile(r'var phrase = new Int8Array\(\[(.*?)\]\);', re.S)
    _CHALLENGE_DATA_LEN_RE = re.compile(r'var data = new Int8Array\((\d+)\);')
    _CHALLENGE_MOD_RE = re.compile(
        r'for\(var i = (\d+); i < data\.length; i\+=1024\) \{\s*data\[i\] = data\[i\] \+ (\d+) > 127'
    )
    _CHALLENGE_COOKIE_RE = re.compile(r'<div id="[^"]*" data-name="([^"]*)" data-domain="([^"]*)"></div>')

    def __init__(self):
        self._use_images = True
        self._session = requests.Session()

    @classmethod
    def _solve_qrator_challenge(cls, html):
        """Решает JS-пазл антибота QRATOR и возвращает (имя_куки, домен,
        значение) для установки в сессию, либо None, если страница не
        похожа на пазл."""
        segments = cls._CHALLENGE_SEGMENT_RE.findall(html)
        phrase_m = cls._CHALLENGE_PHRASE_RE.search(html)
        data_len_m = cls._CHALLENGE_DATA_LEN_RE.search(html)
        cfg_m = cls._CHALLENGE_COOKIE_RE.search(html)
        if not (segments and phrase_m and data_len_m and cfg_m):
            return None

        value = ''
        for part, reversed_flag in segments:
            value += part[::-1] if reversed_flag else part

        phrase = [int(x) for x in phrase_m.group(1).replace('\n', '').split(',') if x.strip()]
        data_len = int(data_len_m.group(1))
        mods = [(int(p), int(d)) for p, d in cls._CHALLENGE_MOD_RE.findall(html)]

        tile = phrase[:]
        for pos, delta in mods:
            v = tile[pos] + delta
            tile[pos] = v - 128 if v > 127 else v

        checksum = tile.count(-127) * (data_len // 1024)

        trim = 5
        for digit in reversed(str(checksum)):
            if digit != '0':
                trim = int(digit)
                break

        cookie_name, cookie_domain = cfg_m.groups()
        return cookie_name, cookie_domain.lstrip('.'), value[:len(value) - trim]

    def _post_graphql(self, query, variables, headers):
        """POST-запрос к GraphQL с обходом JS-пазла антибота QRATOR при необходимости."""
        payload = {'query': query, 'variables': variables}
        merged_headers = {**self.get_headers(), **headers}
        response = self._session.post(
            self.GRAPHQL_URL, json=payload, headers=merged_headers, timeout=self.REQUEST_TIMEOUT,
        )

        for _ in range(self.MAX_CHALLENGE_ATTEMPTS):
            if response.status_code != 429:
                break
            solved = self._solve_qrator_challenge(response.text)
            if not solved:
                break
            cookie_name, cookie_domain, cookie_value = solved
            self._session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)
            logger.info('Citilink: решён JS-пазл антибота QRATOR, повторяю запрос')
            response = self._session.post(
                self.GRAPHQL_URL, json=payload, headers=merged_headers, timeout=self.REQUEST_TIMEOUT,
            )

        # GraphQL-ошибки валидации запроса (например, неподходящее поле images)
        # приходят с кодом 400, но содержат разбираемый JSON с "errors" —
        # отдаём его наверх для обработки фолбэка в _request_page.
        try:
            return response.json()
        except ValueError:
            response.raise_for_status()
            raise

    def _request_page(self, page):
        variables = {
            'filter': {
                'categorySlug': self.CATEGORY_SLUG,
                'compilationPath': [],
                'pagination': {'page': page, 'perPage': self.PER_PAGE},
                'partialPagination': {'offset': 0, 'limit': self.PER_PAGE},
                'conditions': [],
                'sorting': {'id': '', 'direction': 'SORT_DIRECTION_DESC'},
                'popularitySegmentId': 'THREE',
            }
        }
        headers = {
            'Referer': f'https://www.citilink.ru/catalog/{self.CATEGORY_SLUG}/',
            'X-CityId': self.CITY_ID,
        }
        query = self.QUERY if self._use_images else self.QUERY_NO_IMAGES
        data = self._post_graphql(query, variables, headers)
        if data.get('errors'):
            if self._use_images:
                logger.warning('Citilink: поле images недоступно в GraphQL, отключаю его')
                self._use_images = False
                return self._request_page(page)
            raise RuntimeError(data['errors'])
        return data['data']['productsFilter']['record']

    def parse(self) -> list[dict]:
        items = []
        total_pages = None

        for page in range(1, self.MAX_PAGES + 1):
            if total_pages is not None and page > total_pages:
                break

            try:
                record = self._request_page(page)
            except Exception:
                logger.exception('Citilink: ошибка запроса страницы %s', page)
                break

            total_pages = record['pageInfo']['totalPages']
            products = record['products']
            if not products:
                logger.info('Citilink: товары на странице %s не найдены, остановка пагинации', page)
                break

            for good in products:
                try:
                    price = self.parse_price(good['price']['current'])
                    if price is None:
                        continue

                    name = good['name'].strip()
                    product_url = f"https://www.citilink.ru/product/{good['slug']}-{good['id']}/"

                    images = good.get('images') or []
                    image_url = images[0] if images else ''

                    specs = self.parse_ram_specs(name)
                    items.append({
                        'external_id': str(good['id']),
                        'name': name,
                        'brand': self.guess_brand(name),
                        'capacity_gb': specs['capacity_gb'] or 0,
                        'memory_type': specs['memory_type'] or '',
                        'frequency_mhz': specs['frequency_mhz'],
                        'url': product_url,
                        'price': price,
                        'image_url': image_url,
                    })
                except Exception:
                    logger.exception('Citilink: ошибка разбора товара')
                    continue

            self.sleep()

        return items
