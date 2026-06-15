import json
import logging

from .base import BaseParser

logger = logging.getLogger('scraper')


class RegardParser(BaseParser):
    """Парсер каталога ОЗУ магазина Regard (regard.ru).

    Regard — Next.js SPA: список товаров приходит внутри
    <script id="__NEXT_DATA__"> как JSON
    (props.initialState.listing.data[CATEGORY_ID].pages[pageIndex].data).
    """

    marketplace_name = 'Regard'
    marketplace_url = 'https://www.regard.ru/'

    CATALOG_URL = 'https://www.regard.ru/catalog/1010/operativnaya-pamyat'
    CATEGORY_ID = '1010'

    # id города Екатеринбурга в справочнике Regard (см. settings.SCRAPE_CITY).
    # Передаётся кукой city_id — от неё зависят cookieTownId и цены/наличие в SSR-данных.
    CITY_ID = '250'

    def parse(self) -> list[dict]:
        items = []
        cookies = {'city_id': self.CITY_ID}

        for page in range(1, self.MAX_PAGES + 1):
            url = self.CATALOG_URL if page == 1 else f'{self.CATALOG_URL}?page={page}'

            try:
                soup = self.get_soup(url, cookies=cookies)
                script = soup.find('script', id='__NEXT_DATA__')
                data = json.loads(script.string)
            except Exception:
                logger.exception('Regard: ошибка запроса страницы %s', page)
                break

            try:
                page_index = str(page - 1)
                goods = data['props']['initialState']['listing']['data'][self.CATEGORY_ID]['pages'][page_index]['data']
            except (KeyError, TypeError):
                goods = []

            if not goods:
                logger.info('Regard: товары на странице %s не найдены, остановка пагинации', page)
                break

            for good in goods:
                try:
                    name = good['full_title']
                    price = good.get('price')
                    if price is None:
                        continue

                    product_url = f"https://www.regard.ru/product/{good['id']}/{good['seo_url']}"

                    photo = (good.get('photo') or '').lstrip('/')
                    image_url = f'https://www.regard.ru/api/site/cacheimg/goods/{photo}/320' if photo else ''

                    specs = self.parse_ram_specs(name)
                    items.append({
                        'external_id': str(good['id']),
                        'name': name,
                        'brand': good.get('vendor') or self.guess_brand(name),
                        'capacity_gb': specs['capacity_gb'] or 0,
                        'memory_type': specs['memory_type'] or '',
                        'frequency_mhz': specs['frequency_mhz'],
                        'url': product_url,
                        'price': float(price),
                        'image_url': image_url,
                    })
                except Exception:
                    logger.exception('Regard: ошибка разбора товара')
                    continue

            self.sleep()

        return items
