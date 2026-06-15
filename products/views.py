from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Count, F, OuterRef, Prefetch, Subquery
from django.shortcuts import get_object_or_404, redirect, render

from analytics.charts import price_history_chart
from .models import Marketplace, Offer, PriceSnapshot, RAMModule

PAGE_SIZE_CHOICES = [25, 50, 100]
DEFAULT_PAGE_SIZE = PAGE_SIZE_CHOICES[0]

# Соответствие пунктов сортировки и полей/аннотаций для order_by()
SORT_FIELDS = {
    'name': 'name',
    'brand': 'brand',
    'capacity_gb': 'capacity_gb',
    'memory_type': 'memory_type',
    'frequency_mhz': 'frequency_mhz',
    'offers_count': 'offers_count_annotated',
    'min_price': 'min_price',
}

# Пункты выпадающего списка сортировки карточек: (значение sort, подпись)
SORT_OPTIONS = [
    ('name', 'По названию (А-Я)'),
    ('-name', 'По названию (Я-А)'),
    ('min_price', 'Сначала дешевле'),
    ('-min_price', 'Сначала дороже'),
    ('-frequency_mhz', 'Сначала быстрее'),
    ('-offers_count', 'Больше магазинов'),
]


def _parse_decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def product_list(request):
    """Список модулей ОЗУ с фильтрами по названию, бренду, типу памяти, объёму, частоте, площадке и цене."""
    modules = RAMModule.objects.all()

    search = request.GET.get('q', '').strip()
    brand = request.GET.get('brand', '')
    memory_type = request.GET.get('memory_type', '')
    capacity = request.GET.get('capacity', '')
    frequency = request.GET.get('frequency', '')
    marketplace_id = request.GET.get('marketplace', '')
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()

    if search:
        modules = modules.filter(name__icontains=search)
    if brand:
        modules = modules.filter(brand=brand)
    if memory_type:
        modules = modules.filter(memory_type=memory_type)
    if capacity:
        modules = modules.filter(capacity_gb=capacity)
    if frequency:
        modules = modules.filter(frequency_mhz=frequency)
    if marketplace_id:
        modules = modules.filter(offers__marketplace_id=marketplace_id).distinct()

    # Цена самого дешёвого доступного предложения по последнему снимку — используется
    # и для отображения в списке, и для фильтрации по диапазону цен на стороне БД.
    latest_snapshot_price = PriceSnapshot.objects.filter(
        offer_id=OuterRef('pk'), is_available=True
    ).order_by('-scraped_at').values('price')[:1]

    cheapest_offer_price = (
        Offer.objects.filter(ram_module_id=OuterRef('pk'))
        .annotate(latest_price=Subquery(latest_snapshot_price))
        .order_by('latest_price')
        .values('latest_price')[:1]
    )

    offers_count_subquery = (
        Offer.objects.filter(ram_module_id=OuterRef('pk'))
        .order_by()
        .values('ram_module_id')
        .annotate(cnt=Count('pk'))
        .values('cnt')
    )

    modules = modules.annotate(
        min_price=Subquery(cheapest_offer_price),
        offers_count_annotated=Subquery(offers_count_subquery),
    ).prefetch_related(
        Prefetch('offers__snapshots', queryset=PriceSnapshot.objects.order_by('-scraped_at'))
    )

    min_price_value = _parse_decimal(min_price)
    if min_price_value is not None:
        modules = modules.filter(min_price__gte=min_price_value)

    max_price_value = _parse_decimal(max_price)
    if max_price_value is not None:
        modules = modules.filter(min_price__lte=max_price_value)

    sort_param = request.GET.get('sort', 'name')
    sort_field = sort_param.lstrip('-')
    sort_dir = 'desc' if sort_param.startswith('-') else 'asc'
    if sort_field not in SORT_FIELDS:
        sort_field, sort_dir, sort_param = 'name', 'asc', 'name'

    order_field = F(SORT_FIELDS[sort_field])
    order_expr = order_field.desc(nulls_last=True) if sort_dir == 'desc' else order_field.asc(nulls_last=True)
    modules = modules.order_by(order_expr, 'id')

    try:
        page_size = int(request.GET.get('page_size', DEFAULT_PAGE_SIZE))
    except ValueError:
        page_size = DEFAULT_PAGE_SIZE
    if page_size not in PAGE_SIZE_CHOICES:
        page_size = DEFAULT_PAGE_SIZE

    paginator = Paginator(modules, page_size)
    page_obj = paginator.get_page(request.GET.get('page'))

    query_params = request.GET.copy()
    query_params.pop('page', None)

    context = {
        'modules': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'query_params': query_params.urlencode(),
        'sort_options': SORT_OPTIONS,
        'selected_sort': sort_param,
        'page_size': page_size,
        'page_size_choices': PAGE_SIZE_CHOICES,
        'brands': RAMModule.objects.exclude(brand='').order_by('brand').values_list('brand', flat=True).distinct(),
        'memory_types': RAMModule.MEMORY_TYPE_CHOICES,
        'capacities': RAMModule.objects.order_by('capacity_gb').values_list('capacity_gb', flat=True).distinct(),
        'frequencies': RAMModule.objects.exclude(frequency_mhz__isnull=True).order_by('frequency_mhz').values_list('frequency_mhz', flat=True).distinct(),
        'marketplaces': Marketplace.objects.all(),
        'search': search,
        'selected_brand': brand,
        'selected_memory_type': memory_type,
        'selected_capacity': capacity,
        'selected_frequency': frequency,
        'selected_marketplace': marketplace_id,
        'min_price': min_price,
        'max_price': max_price,
    }
    return render(request, 'products/product_list.html', context)


def product_detail(request, pk):
    """Страница модуля ОЗУ с таблицей предложений и графиком истории цен."""
    module = get_object_or_404(RAMModule, pk=pk)
    offers = module.offers.select_related('marketplace').order_by('marketplace__name')

    context = {
        'module': module,
        'offers': offers,
        'chart_div': price_history_chart(module),
    }
    return render(request, 'products/product_detail.html', context)


def compare(request):
    """Сравнение 2-4 модулей ОЗУ по характеристикам и ценам на разных площадках."""
    ids = [pk for pk in request.GET.getlist('ids') if pk.isdigit()]

    modules_by_id = RAMModule.objects.filter(pk__in=ids).prefetch_related(
        Prefetch('offers__snapshots', queryset=PriceSnapshot.objects.order_by('-scraped_at')),
        'offers__marketplace',
    ).in_bulk()
    modules = [modules_by_id[int(pk)] for pk in ids if int(pk) in modules_by_id][:4]

    error = None
    if len(modules) < 2:
        error = 'Выберите от 2 до 4 модулей в каталоге, чтобы сравнить их.'

    marketplace_rows = []
    if not error:
        for marketplace in Marketplace.objects.filter(is_active=True):
            cells = []
            for module in modules:
                offer = next((o for o in module.offers.all() if o.marketplace_id == marketplace.id), None)
                cells.append(offer.latest_price if offer else None)
            marketplace_rows.append({'marketplace': marketplace, 'cells': cells})

    context = {
        'modules': modules,
        'marketplace_rows': marketplace_rows,
        'error': error,
    }
    return render(request, 'products/compare.html', context)


def trigger_scrape(request):
    """Запускает парсинг всех (или одной) площадок по кнопке из интерфейса."""
    if request.method == 'POST':
        source = request.POST.get('source') or None
        try:
            if source:
                call_command('scrape', source=source)
            else:
                call_command('scrape')
            messages.success(request, 'Парсинг успешно завершён.')
        except Exception as exc:
            messages.error(request, f'Ошибка при запуске парсинга: {exc}')

    return redirect('products:product_list')
