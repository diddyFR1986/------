import asyncio
import logging

import zendriver as zd
from bs4 import BeautifulSoup

from .base import BaseParser

logger = logging.getLogger('scraper')


class DNSParser(BaseParser):
    """Парсер каталога ОЗУ магазина DNS (dns-shop.ru).

    DNS защищён антибот-системой Qrator, которая блокирует обычные HTTP-запросы
    (requests/urllib). zendriver управляет настоящим Chrome через CDP и проходит
    проверку — страница рендерится целиком, включая цены, подгружаемые через JS.
    """

    marketplace_name = 'DNS'
    marketplace_url = 'https://www.dns-shop.ru/'

    CATALOG_URL = 'https://www.dns-shop.ru/catalog/17a89a3916404e77/operativnaa-pamat-dimm/'

    # ~913 товаров по 24 на странице (~39 страниц); запас на случай роста каталога.
    MAX_PAGES = 45

    # Время ожидания после загрузки страницы, чтобы JS успел подгрузить цены (сек).
    RENDER_DELAY = 5

    # GUID города в справочнике DNS (https://restapi.dns-shop.ru/v1/get-city-list).
    # Соответствует settings.SCRAPE_CITY = "Екатеринбург".
    CITY_ID = '83878977-f329-11dd-9648-00151716f9f5'

    def parse(self) -> list[dict]:
        return asyncio.run(self._parse())

    async def _set_city(self, browser):
        """Выставляет город DNS через city-service, чтобы цены и наличие
        в каталоге соответствовали settings.SCRAPE_CITY."""
        tab = await browser.get(self.marketplace_url)
        await tab.sleep(3)
        js = '''(async () => {
            await fetch('https://www.dns-shop.ru/city-service/set-city/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({cityId: '%s'})
            });
        })()''' % self.CITY_ID
        await tab.evaluate(js, await_promise=True)

    async def _parse(self) -> list[dict]:
        items = []
        browser = await zd.start(headless=True)

        try:
            try:
                await self._set_city(browser)
            except Exception:
                logger.exception('DNS: не удалось выставить город %s', self.CITY)

            for page in range(1, self.MAX_PAGES + 1):
                url = self.CATALOG_URL if page == 1 else f'{self.CATALOG_URL}?p={page}'

                try:
                    tab = await browser.get(url)
                    await tab.sleep(self.RENDER_DELAY)
                    html = await tab.get_content()

                    soup = BeautifulSoup(html, 'lxml')
                    cards = soup.select('div.catalog-product[data-code]')
                    if not cards:
                        # страница могла не успеть прорендериться — пробуем ещё раз
                        await tab.sleep(self.RENDER_DELAY)
                        html = await tab.get_content()
                        soup = BeautifulSoup(html, 'lxml')
                        cards = soup.select('div.catalog-product[data-code]')
                except Exception:
                    logger.exception('DNS: ошибка запроса страницы %s', page)
                    break

                if not cards:
                    logger.info('DNS: товары на странице %s не найдены, остановка пагинации', page)
                    break

                for card in cards:
                    try:
                        name_el = card.select_one('.catalog-product__name')
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        href = name_el.get('href', '')
                        if not href:
                            continue
                        product_url = href if href.startswith('http') else f'https://www.dns-shop.ru{href}'

                        img_el = card.select_one('.catalog-product__image img')
                        image_url = (img_el.get('src') or img_el.get('data-src') or '') if img_el else ''

                        price_el = card.select_one('.product-buy__price')
                        if not price_el:
                            continue
                        # внутри может быть .product-buy__prev со старой ценой
                        # (при скидке) — убираем её перед извлечением текста
                        prev_price_el = price_el.select_one('.product-buy__prev')
                        if prev_price_el:
                            prev_price_el.extract()
                        price = self.parse_price(price_el.get_text(strip=True))
                        if price is None:
                            continue

                        specs = self.parse_ram_specs(name)
                        items.append({
                            'external_id': card['data-code'],
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
                        logger.exception('DNS: ошибка разбора товара')
                        continue
        finally:
            await browser.stop()

        return items
