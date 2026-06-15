from django.db import models


class Marketplace(models.Model):
    """Торговая площадка (магазин), на которой парсятся товары."""

    name = models.CharField(max_length=100, verbose_name='Название')
    url = models.URLField(verbose_name='URL площадки')
    is_active = models.BooleanField(default=True, verbose_name='Активна')

    class Meta:
        verbose_name = 'Торговая площадка'
        verbose_name_plural = 'Торговые площадки'

    def __str__(self):
        return self.name


class RAMModule(models.Model):
    """Уникальный модуль ОЗУ — может продаваться на нескольких площадках."""

    DDR2 = 'DDR2'
    DDR3 = 'DDR3'
    DDR4 = 'DDR4'
    DDR5 = 'DDR5'
    MEMORY_TYPE_CHOICES = [
        (DDR2, 'DDR2'),
        (DDR3, 'DDR3'),
        (DDR4, 'DDR4'),
        (DDR5, 'DDR5'),
    ]

    name = models.CharField(max_length=255, verbose_name='Название')
    brand = models.CharField(max_length=100, verbose_name='Бренд')
    part_number = models.CharField(
        max_length=100, null=True, blank=True, unique=True, verbose_name='Артикул'
    )
    capacity_gb = models.IntegerField(verbose_name='Объём, ГБ')
    memory_type = models.CharField(
        max_length=10, choices=MEMORY_TYPE_CHOICES, blank=True, verbose_name='Тип памяти'
    )
    frequency_mhz = models.IntegerField(null=True, blank=True, verbose_name='Частота, МГц')
    image_url = models.URLField(blank=True, verbose_name='Изображение')

    class Meta:
        verbose_name = 'Модуль ОЗУ'
        verbose_name_plural = 'Модули ОЗУ'

    def __str__(self):
        return self.name

    @property
    def offers_count(self):
        return self.offers.count()

    @property
    def best_offer(self):
        """Предложение с минимальной актуальной ценой среди доступных."""
        best = None
        best_price = None
        for offer in self.offers.all():
            snapshots = list(offer.snapshots.all())
            if not snapshots or not snapshots[0].is_available:
                continue
            if best_price is None or snapshots[0].price < best_price:
                best_price = snapshots[0].price
                best = offer
        return best

    @property
    def latest_price(self):
        """Минимальная актуальная цена среди всех предложений."""
        best = self.best_offer
        return best.latest_price if best else None

    @property
    def price_trend(self):
        """Изменение цены лучшего предложения по сравнению с предыдущим снимком."""
        best = self.best_offer
        return best.price_trend if best else None


class Offer(models.Model):
    """Предложение конкретной площадки для модуля ОЗУ."""

    ram_module = models.ForeignKey(
        RAMModule, on_delete=models.CASCADE, related_name='offers', verbose_name='Модуль ОЗУ'
    )
    marketplace = models.ForeignKey(
        Marketplace, on_delete=models.CASCADE, related_name='offers', verbose_name='Площадка'
    )
    external_id = models.CharField(max_length=100, verbose_name='ID товара на площадке')
    name = models.CharField(max_length=255, verbose_name='Название')
    url = models.URLField(verbose_name='Ссылка на товар')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        verbose_name = 'Предложение'
        verbose_name_plural = 'Предложения'
        # один и тот же товар на площадке не должен дублироваться
        unique_together = ('marketplace', 'external_id')

    def __str__(self):
        return f'{self.name} ({self.marketplace.name})'

    @property
    def latest_price(self):
        """Последняя известная цена предложения."""
        snapshots = list(self.snapshots.all())
        return snapshots[0].price if snapshots else None

    @property
    def price_trend(self):
        """Изменение цены по сравнению с предыдущим снимком: {'direction': 'up'|'down', 'percent': Decimal} либо None."""
        snapshots = list(self.snapshots.all())[:2]
        if len(snapshots) < 2:
            return None
        latest, previous = snapshots
        if not previous.price or latest.price == previous.price:
            return None
        diff = latest.price - previous.price
        percent = abs(diff) / previous.price * 100
        return {'direction': 'up' if diff > 0 else 'down', 'percent': percent}


class PriceSnapshot(models.Model):
    """Снимок цены предложения на момент парсинга — формирует историю цен."""

    offer = models.ForeignKey(
        Offer, on_delete=models.CASCADE, related_name='snapshots', verbose_name='Предложение'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена')
    is_available = models.BooleanField(default=True, verbose_name='В наличии')
    scraped_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата парсинга')

    class Meta:
        verbose_name = 'Снимок цены'
        verbose_name_plural = 'Снимки цен'
        ordering = ['-scraped_at']

    def __str__(self):
        return f'{self.offer.name} — {self.price} ({self.scraped_at:%Y-%m-%d %H:%M})'
