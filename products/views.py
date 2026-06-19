from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Count, F, OuterRef, Prefetch, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
    """Список модулей ОЗУ с фильтрами."""
    modules = RAMModule.objects.all()

    search = request.GET.get('q', '').strip()
    brands_selected = request.GET.getlist('brand')
    memory_type = request.GET.get('memory_type', '')
    capacity_min = request.GET.get('capacity_min', '').strip()
    capacity_max = request.GET.get('capacity_max', '').strip()
    frequency_min = request.GET.get('frequency_min', '').strip()
    frequency_max = request.GET.get('frequency_max', '').strip()
    marketplace_id = request.GET.get('marketplace', '')
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()

    if search:
        modules = modules.filter(name__icontains=search)
    if brands_selected:
        modules = modules.filter(brand__in=brands_selected)
    if memory_type:
        modules = modules.filter(memory_type=memory_type)
    try:
        if capacity_min:
            modules = modules.filter(capacity_gb__gte=int(capacity_min))
        if capacity_max:
            modules = modules.filter(capacity_gb__lte=int(capacity_max))
    except ValueError:
        pass
    try:
        if frequency_min:
            modules = modules.filter(frequency_mhz__gte=int(frequency_min))
        if frequency_max:
            modules = modules.filter(frequency_mhz__lte=int(frequency_max))
    except ValueError:
        pass
    if marketplace_id:
        modules = modules.filter(
            offers__marketplace_id=marketplace_id
        ).distinct()

    # Цена дешёвого доступного предложения по последнему снимку —
    # используется и для отображения, и для фильтрации по цене в БД.
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
        Prefetch(
            'offers__snapshots',
            queryset=PriceSnapshot.objects.order_by('-scraped_at'),
        )
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
    if sort_dir == 'desc':
        order_expr = order_field.desc(nulls_last=True)
    else:
        order_expr = order_field.asc(nulls_last=True)
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
    compare_ids = set(request.session.get('compare_ids', []))

    context = {
        'modules': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'query_params': query_params.urlencode(),
        'sort_options': SORT_OPTIONS,
        'selected_sort': sort_param,
        'page_size': page_size,
        'page_size_choices': PAGE_SIZE_CHOICES,
        'brands': (
            RAMModule.objects.exclude(brand='')
            .order_by('brand').values_list('brand', flat=True).distinct()
        ),
        'memory_types': RAMModule.MEMORY_TYPE_CHOICES,
        'marketplaces': Marketplace.objects.all(),
        'search': search,
        'selected_brands': brands_selected,
        'selected_memory_type': memory_type,
        'capacity_min': capacity_min,
        'capacity_max': capacity_max,
        'frequency_min': frequency_min,
        'frequency_max': frequency_max,
        'selected_marketplace': marketplace_id,
        'min_price': min_price,
        'max_price': max_price,
        'compare_ids': compare_ids,
    }
    return render(request, 'products/product_list.html', context)


def product_detail(request, pk):
    """Страница модуля ОЗУ с таблицей предложений и графиком истории цен."""
    module = get_object_or_404(RAMModule, pk=pk)
    offers = list(
        module.offers.select_related('marketplace')
        .order_by('marketplace__name')
    )
    # Sort by price so first offer is cheapest (for "дешевле всех" badge)
    offers.sort(key=lambda o: (o.latest_price is None, o.latest_price))

    compare_ids = set(request.session.get('compare_ids', []))
    context = {
        'module': module,
        'offers': offers,
        'chart_div': price_history_chart(module),
        'compare_ids': compare_ids,
    }
    return render(request, 'products/product_detail.html', context)


def _get_compare_ids(request):
    """Читает список id модулей для сравнения из сессии."""
    return list(request.session.get('compare_ids', []))


def compare(request):
    """Сравнение 2-4 модулей ОЗУ по характеристикам и ценам."""
    ids = _get_compare_ids(request)

    modules_by_id = RAMModule.objects.filter(pk__in=ids).prefetch_related(
        Prefetch(
            'offers__snapshots',
            queryset=PriceSnapshot.objects.order_by('-scraped_at'),
        ),
        'offers__marketplace',
    ).in_bulk()

    # Отбрасываем удалённые модули и перезаписываем сессию (KTD6, R8)
    valid_ids = [pk for pk in ids if pk in modules_by_id]
    if len(valid_ids) != len(ids):
        request.session['compare_ids'] = valid_ids

    modules = [modules_by_id[pk] for pk in valid_ids][:4]

    error = None
    if len(modules) < 2:
        error = 'Выберите от 2 до 4 модулей в каталоге, чтобы сравнить их.'

    marketplace_rows = []
    if not error:
        for marketplace in Marketplace.objects.filter(is_active=True):
            raw_prices = []
            for module in modules:
                offer = next(
                    (o for o in module.offers.all()
                     if o.marketplace_id == marketplace.id),
                    None,
                )
                raw_prices.append(offer.latest_price if offer else None)
            existing = [p for p in raw_prices if p is not None]
            min_price_in_row = min(existing) if existing else None
            cells = [
                {
                    'price': p,
                    'is_best': (
                        p is not None
                        and p == min_price_in_row
                        and len(existing) > 1
                    ),
                }
                for p in raw_prices
            ]
            marketplace_rows.append(
                {'marketplace': marketplace, 'cells': cells}
            )

    # Подсветка лучших значений в сравнительной таблице
    prices = [m.latest_price for m in modules if m.latest_price is not None]
    overall_min = min(prices) if len(prices) > 1 else None
    cheapest_ids = {
        m.pk for m in modules
        if m.latest_price is not None and m.latest_price == overall_min
    }

    freqs = [m.frequency_mhz for m in modules if m.frequency_mhz]
    best_freq = max(freqs) if len(freqs) > 1 else None
    best_freq_ids = {
        m.pk for m in modules if m.frequency_mhz == best_freq
    } if best_freq else set()

    caps = [m.capacity_gb for m in modules if m.capacity_gb]
    best_cap = max(caps) if len(caps) > 1 else None
    best_cap_ids = {
        m.pk for m in modules if m.capacity_gb == best_cap
    } if best_cap else set()

    cls_vals = [m.timing_cl for m in modules if m.timing_cl is not None]
    best_cl = min(cls_vals) if len(cls_vals) > 1 else None  # меньше = лучше
    best_cl_ids = {
        m.pk for m in modules if m.timing_cl == best_cl
    } if best_cl else set()

    context = {
        'modules': modules,
        'marketplace_rows': marketplace_rows,
        'cheapest_ids': cheapest_ids,
        'best_freq_ids': best_freq_ids,
        'best_cap_ids': best_cap_ids,
        'best_cl_ids': best_cl_ids,
        'error': error,
    }
    return render(request, 'products/compare.html', context)


@require_POST
def compare_toggle(request, pk):
    """Добавляет или удаляет pk из списка сравнения в сессии (лимит 4)."""
    ids = _get_compare_ids(request)
    if pk in ids:
        ids.remove(pk)
    elif len(ids) < 4:
        ids.append(pk)
    request.session['compare_ids'] = ids
    return JsonResponse({'ids': ids, 'count': len(ids)})


@require_POST
def compare_clear(request):
    """Обнуляет список сравнения в сессии."""
    request.session['compare_ids'] = []
    return redirect('products:product_list')


@require_POST
def compare_remove(request, pk):
    """Удаляет один модуль из сравнения и возвращает на /compare/."""
    ids = _get_compare_ids(request)
    if pk in ids:
        ids.remove(pk)
    request.session['compare_ids'] = ids
    return redirect('products:compare')


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
