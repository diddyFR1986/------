import logging

import requests

from .base import BaseParser

logger = logging.getLogger('scraper')


class MVideoParser(BaseParser):
    """Парсер каталога ОЗУ магазина MVideo (mvideo.ru).

    Каталог рендерится на клиенте, товары запрашиваются через внутренний
    BFF API (/bff/products), которым пользуется сам сайт. Этому API нужны
    куки региона/города (MVID_CITY_ID и т.п.), которые сервер выставляет
    при обычной загрузке страницы категории.
    """

    marketplace_name = 'MVideo'
    marketplace_url = 'https://www.mvideo.ru/'

    CATEGORY_URL = 'https://www.mvideo.ru/komputernye-komplektuushhie-5427/operativnaya-pamyat-5442'
    CATEGORY_ID = '5442'
    PRODUCTS_URL = 'https://www.mvideo.ru/bff/products'
    SET_LOCATION_URL = 'https://www.mvideo.ru/bff/region/setLocation'
    LIMIT = 60

    MAX_PAGES = 15

    # cityId Екатеринбурга в BFF MVideo (см. settings.SCRAPE_CITY)
    CITY_ID = 'CityCZ_2030'

    def get_headers(self):
        headers = super().get_headers()
        headers['Accept'] = 'application/json'
        headers['Content-Type'] = 'application/json'
        headers['Referer'] = self.CATEGORY_URL
        headers['x-client-info'] = 'eyJ3IjoxMjgwLCJoIjo3MjAsInAiOjF9'
        return headers

    def _set_city(self, session):
        """Переключает регион сессии на settings.SCRAPE_CITY, чтобы /bff/products
        возвращал цены и наличие для нужного города."""
        try:
            session.post(
                self.SET_LOCATION_URL,
                json={'cityId': self.CITY_ID},
                headers=self.get_headers(),
                timeout=self.REQUEST_TIMEOUT,
            )
        except Exception:
            logger.exception('MVideo: не удалось выставить город %s', self.CITY)

    def parse(self) -> list[dict]:
        items = []

        session = requests.Session()
        try:
            session.get(self.CATEGORY_URL, headers=self.get_headers(), timeout=self.REQUEST_TIMEOUT)
        except Exception:
            logger.exception('MVideo: ошибка загрузки страницы категории')
            return items

        self._set_city(session)

        cursor_id = ''
        for page in range(1, self.MAX_PAGES + 1):
            payload = {
                'limit': self.LIMIT,
                'cursorId': cursor_id,
                'enrich': True,
                'filters': [{'id': 'category', 'valuesId': [self.CATEGORY_ID]}],
                'sortBy': 'popularity',
                'sortDirection': 'desc',
                'isGettingBonusRoubles': True,
            }

            try:
                response = session.post(
                    self.PRODUCTS_URL, json=payload, headers=self.get_headers(), timeout=self.REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                body = response.json()['body']
            except Exception:
                logger.exception('MVideo: ошибка запроса страницы %s', page)
                break

            products = body.get('items', [])
            if not products:
                logger.info('MVideo: товары на странице %s не найдены, остановка пагинации', page)
                break

            for good in products:
                try:
                    price = good.get('price', {}).get('salePrice')
                    if price is None:
                        continue

                    name = good['name'].strip()
                    product_url = f"https://www.mvideo.ru{good['slug']}"

                    images = good.get('images') or []
                    image_url = f'https://img.mvideo.ru/{images[0]}' if images else ''

                    specs = self.parse_ram_specs(name)
                    items.append({
                        'external_id': str(good['productId']),
                        'name': name,
                        'brand': self.guess_brand(name),
                        'capacity_gb': specs['capacity_gb'] or 0,
                        'memory_type': specs['memory_type'] or '',
                        'frequency_mhz': specs['frequency_mhz'],
                        'url': product_url,
                        'price': float(price),
                        'image_url': image_url,
                    })
                except Exception:
                    logger.exception('MVideo: ошибка разбора товара')
                    continue

            cursor_id = body.get('cursorId')
            if cursor_id is None:
                break

            self.sleep()

        return items
