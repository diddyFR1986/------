import plotly.graph_objs as go
import plotly.offline as opy
from django.db.models import Avg, Count, OuterRef, Subquery

from products.models import Offer, PriceSnapshot, RAMModule


def _annotate_current_price(queryset):
    """Аннотирует queryset предложений последней известной ценой (current_price)."""
    latest_price = (
        PriceSnapshot.objects.filter(offer=OuterRef('pk'))
        .order_by('-scraped_at')
        .values('price')[:1]
    )
    return queryset.annotate(current_price=Subquery(latest_price))


def price_history_chart(module):
    """Линейный график динамики цены модуля — отдельная линия на каждый магазин."""
    fig = go.Figure()
    has_data = False

    for offer in module.offers.select_related('marketplace').all():
        snapshots = offer.snapshots.order_by('scraped_at')
        if not snapshots:
            continue
        has_data = True
        x = [snapshot.scraped_at for snapshot in snapshots]
        y = [float(snapshot.price) for snapshot in snapshots]
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines+markers', name=offer.marketplace.name))

    if not has_data:
        return None

    fig.update_layout(
        title=f'История цены: {module.name}',
        xaxis_title='Дата',
        yaxis_title='Цена, ₽',
        margin=dict(t=40, b=40, l=40, r=20),
    )
    return opy.plot(fig, auto_open=False, output_type='div')


def avg_price_by_marketplace_chart():
    """Столбчатый график: средняя текущая цена предложений по площадкам."""
    offers = _annotate_current_price(Offer.objects.all())
    data = (
        offers.exclude(current_price__isnull=True)
        .values('marketplace__name')
        .annotate(avg_price=Avg('current_price'))
        .order_by('marketplace__name')
    )
    if not data:
        return None

    names = [row['marketplace__name'] for row in data]
    values = [round(float(row['avg_price']), 2) for row in data]

    fig = go.Figure(data=[go.Bar(x=names, y=values)])
    fig.update_layout(
        title='Средняя цена по площадкам',
        xaxis_title='Площадка',
        yaxis_title='Цена, ₽',
        margin=dict(t=40, b=40, l=40, r=20),
    )
    return opy.plot(fig, auto_open=False, output_type='div')


def ddr_distribution_chart():
    """Круговая диаграмма: распределение модулей DDR4 vs DDR5."""
    data = (
        RAMModule.objects.exclude(memory_type='')
        .values('memory_type')
        .annotate(count=Count('id'))
        .order_by('memory_type')
    )
    if not data:
        return None

    labels = [row['memory_type'] for row in data]
    values = [row['count'] for row in data]

    fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
    fig.update_layout(title='Распределение DDR4 vs DDR5', margin=dict(t=40, b=20, l=20, r=20))
    return opy.plot(fig, auto_open=False, output_type='div')


def products_by_brand_chart():
    """Столбчатый график: количество уникальных модулей ОЗУ по брендам."""
    data = (
        RAMModule.objects.exclude(brand='')
        .values('brand')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    if not data:
        return None

    brands = [row['brand'] for row in data]
    counts = [row['count'] for row in data]

    fig = go.Figure(data=[go.Bar(x=brands, y=counts)])
    fig.update_layout(
        title='Количество модулей ОЗУ по брендам',
        xaxis_title='Бренд',
        yaxis_title='Количество',
        margin=dict(t=40, b=40, l=40, r=20),
    )
    return opy.plot(fig, auto_open=False, output_type='div')


def top10_cheapest():
    """Топ-10 самых дешёвых предложений на текущий момент."""
    offers = _annotate_current_price(Offer.objects.select_related('marketplace', 'ram_module'))
    return (
        offers.exclude(current_price__isnull=True)
        .order_by('current_price')[:10]
    )
