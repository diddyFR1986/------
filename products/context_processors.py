def compare_count(request):
    """Добавляет compare_count во все шаблоны — без обращения к БД (KTD4)."""
    return {'compare_count': len(request.session.get('compare_ids', []))}
