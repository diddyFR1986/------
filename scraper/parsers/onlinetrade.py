import asyncio
import logging
import re

import zendriver as zd
from bs4 import BeautifulSoup

from .base import BaseParser

logger = logging.getLogger('scraper')


class OnlinetradeParser(BaseParser):
    """Парсер каталога ОЗУ магазина Onlinetrade (onlinetrade.ru).

    Каталог защищён антибот-системой servicepipe.ru: в headless-режиме
    она отдаёт страницу с капчей ("разверните картинку"), но в обычном
    (не headless) режиме отдаёт промежуточную страницу-заглушку с JS-пазлом,
    которая сама разрешается через несколько секунд — см. RENDER_ATTEMPTS.
    """

    marketplace_name = 'Onlinetrade'
    marketplace_url = 'https://www.onlinetrade.ru/'

    CATALOG_URL = 'https://www.onlinetrade.ru/catalogue/operativnaya_pamyat-c341/'

    PER_PAGE = 45
    # ~315 товаров / 45 на страницу = 7 страниц, с запасом на рост каталога
    MAX_PAGES = 20

    # Время ожидания после загрузки страницы, чтобы JS успел подгрузить карточки (сек).
    RENDER_DELAY = 8
    # Сколько раз повторно ждать RENDER_DELAY, если карточки ещё не появились.
    RENDER_ATTEMPTS = 3

    # id города Екатеринбурга в справочнике Onlinetrade (см. settings.SCRAPE_CITY).
    # Передаётся параметром ?c= — сайт выставляет по нему куки user_c/user_city,
    # от которых зависят цены и наличие в каталоге.
    CITY_ID = '35'

    def parse(self) -> list[dict]:
        return asyncio.run(self._parse())

    async def _parse(self) -> list[dict]:
        items = []
        browser = await zd.start(headless=False)

        try:
            for pg in range(self.MAX_PAGES):
                url = f'{self.CATALOG_URL}?per_page={self.PER_PAGE}&page={pg}&c={self.CITY_ID}'

                try:
                    tab = await browser.get(url)
                    cards = []
                    html = ''
                    # антибот servicepipe иногда отдаёт промежуточную
                    # страницу-заглушку с JS-пазлом — даём странице
                    # несколько попыток дорендериться
                    for _ in range(self.RENDER_ATTEMPTS):
                        await tab.sleep(self.RENDER_DELAY)
                        html = await tab.get_content()
                        soup = BeautifulSoup(html, 'lxml')
                        cards = soup.select('.indexGoods__item')
                        if cards:
                            break
                except Exception:
                    logger.exception('Onlinetrade: ошибка запроса страницы %s', pg)
                    break

                if not cards:
                    if 'sp_rotated_captcha' in html:
                        # промежуточная заглушка не успела разрешиться сама и
                        # переросла в интерактивную капчу — далее тоже капча,
                        # ожиданием не обойти, прерываем пагинацию
                        logger.warning(
                            'Onlinetrade: антибот servicepipe показал капчу на странице %s, остановка пагинации', pg,
                        )
                    else:
                        logger.info('Onlinetrade: товары на странице %s не найдены, остановка пагинации', pg)
                    break

                for card in cards:
                    try:
                        name_el = card.select_one('.indexGoods__item__name')
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        href = name_el.get('href', '')
                        if not href:
                            continue
                        product_url = href if href.startswith('http') else f'https://www.onlinetrade.ru{href}'

                        img_el = card.select_one('.indexGoods__item__image img')
                        image_url = img_el.get('src', '') if img_el else ''

                        # .js__actualPrice — текущая цена (обычная или
                        # сниженная); старая цена при скидке лежит в
                        # отдельном .priceOld и сюда не попадает
                        price_el = card.select_one('.indexGoods__item__price .js__actualPrice')
                        if not price_el:
                            continue
                        price = self.parse_price(price_el.get_text(strip=True))
                        if price is None:
                            continue

                        id_match = re.search(r'-(\d+)\.html', href)
                        external_id = id_match.group(1) if id_match else self.extract_external_id(product_url)

                        specs = self.parse_ram_specs(name)
                        items.append({
                            'external_id': external_id,
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
                        logger.exception('Onlinetrade: ошибка разбора товара')
                        continue
        finally:
            await browser.stop()

        return items
