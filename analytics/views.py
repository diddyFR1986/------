from django.shortcuts import render

from . import charts


def dashboard(request):
    """Дашборд аналитики цен на ОЗУ: графики и таблица топ-10 предложений."""
    context = {
        'avg_price_chart': charts.avg_price_by_marketplace_chart(),
        'ddr_chart': charts.ddr_distribution_chart(),
        'brand_chart': charts.products_by_brand_chart(),
        'top10': charts.top10_cheapest(),
    }
    return render(request, 'analytics/dashboard.html', context)
