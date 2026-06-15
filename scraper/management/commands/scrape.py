import logging

from django.core.management.base import BaseCommand

from products.models import Marketplace, Offer, PriceSnapshot, RAMModule
from scraper.parsers.citilink import CitilinkParser
from scraper.parsers.dns import DNSParser
from scraper.parsers.mvideo import MVideoParser
from scraper.parsers.onlinetrade import OnlinetradeParser
from scraper.parsers.regard import RegardParser

logger = logging.getLogger('scraper')

PARSERS = {
    'dns': DNSParser,
    'mvideo': MVideoParser,
    'regard': RegardParser,
    'onlinetrade': OnlinetradeParser,
    'citilink': CitilinkParser,
}


class Command(BaseCommand):
    help = 'Запускает парсинг цен на модули ОЗУ с торговых площадок'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            choices=list(PARSERS.keys()),
            help='Запустить парсер только для одной площадки (dns, mvideo, regard, onlinetrade, citilink)',
        )

    def handle(self, *args, **options):
        source = options.get('source')
        sources = [source] if source else list(PARSERS.keys())

        for key in sources:
            parser_class = PARSERS[key]
            marketplace_name = parser_class.marketplace_name

            try:
                marketplace = Marketplace.objects.get(name=marketplace_name)
            except Marketplace.DoesNotExist:
                logger.error('Площадка "%s" не найдена в базе данных', marketplace_name)
                continue

            if not marketplace.is_active:
                self.stdout.write(f'{marketplace_name}: площадка отключена, пропуск')
                continue

            self.stdout.write(f'Парсинг площадки: {marketplace_name}...')

            try:
                results = parser_class().parse()
            except Exception:
                logger.exception('Парсер %s завершился с ошибкой', marketplace_name)
                continue

            created_count, updated_count = self._save_results(marketplace, results, parser_class)

            self.stdout.write(self.style.SUCCESS(
                f'{marketplace_name}: получено {len(results)}, '
                f'новых товаров {created_count}, обновлено {updated_count}'
            ))

    def _save_results(self, marketplace, results, parser_class):
        created_count = 0
        updated_count = 0

        for item in results:
            try:
                ram_module = self._resolve_ram_module(marketplace, item, parser_class)

                offer, created = Offer.objects.get_or_create(
                    marketplace=marketplace,
                    external_id=item['external_id'],
                    defaults={
                        'ram_module': ram_module,
                        'name': item['name'],
                        'url': item['url'],
                    },
                )

                if created:
                    created_count += 1
                else:
                    offer.ram_module = ram_module
                    offer.name = item['name']
                    offer.url = item['url']
                    offer.save()
                    updated_count += 1

                PriceSnapshot.objects.create(
                    offer=offer,
                    price=item['price'],
                    is_available=item.get('is_available', True),
                )
            except Exception:
                logger.exception('Ошибка сохранения товара "%s"', item.get('name'))
                continue

        return created_count, updated_count

    def _resolve_ram_module(self, marketplace, item, parser_class):
        """Находит или создаёт RAMModule для товара.

        Если в названии нашёлся артикул производителя — модуль
        дедуплицируется по нему между площадками. Иначе при повторном
        парсинге сохраняется ранее привязанный модуль, а для нового
        предложения создаётся отдельный (не дедуплицируемый) модуль.
        """
        part_number = parser_class.extract_part_number(item['name'])
        image_url = item.get('image_url') or ''

        if part_number:
            ram_module, _ = RAMModule.objects.get_or_create(
                part_number=part_number,
                defaults={
                    'name': item['name'],
                    'brand': item['brand'],
                    'capacity_gb': item['capacity_gb'],
                    'memory_type': item['memory_type'],
                    'frequency_mhz': item['frequency_mhz'],
                    'image_url': image_url,
                },
            )
        else:
            existing_offer = Offer.objects.filter(
                marketplace=marketplace, external_id=item['external_id']
            ).first()
            if existing_offer:
                ram_module = existing_offer.ram_module
            else:
                ram_module = RAMModule.objects.create(
                    name=item['name'],
                    brand=item['brand'],
                    part_number=None,
                    capacity_gb=item['capacity_gb'],
                    memory_type=item['memory_type'],
                    frequency_mhz=item['frequency_mhz'],
                    image_url=image_url,
                )

        self._fill_missing_specs(ram_module, item, image_url)

        return ram_module

    # Поля модуля, которые можно дозаполнить данными с другой площадки,
    # если на момент создания модуля они остались пустыми/неизвестными.
    FILLABLE_FIELDS = {
        'brand': lambda value: not value or value == 'Unknown',
        'memory_type': lambda value: not value,
        'frequency_mhz': lambda value: not value,
        'capacity_gb': lambda value: not value,
        'image_url': lambda value: not value,
    }

    @classmethod
    def _fill_missing_specs(cls, ram_module, item, image_url):
        """Дозаполняет пустые характеристики модуля данными из новой площадки."""
        new_values = {**item, 'image_url': image_url}

        update_fields = []
        for field, is_empty in cls.FILLABLE_FIELDS.items():
            current = getattr(ram_module, field)
            new_value = new_values.get(field)
            if is_empty(current) and new_value and not is_empty(new_value):
                setattr(ram_module, field, new_value)
                update_fields.append(field)

        if update_fields:
            ram_module.save(update_fields=update_fields)
