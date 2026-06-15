import re

from django.db import migrations

PART_NUMBER_RE = re.compile(r'[A-Z0-9][A-Z0-9\-/]{5,}[A-Z0-9]', re.IGNORECASE)
PART_NUMBER_STOP_RE = re.compile(
    r'^(?:DDR[2345][A-Z]{0,2}(?:-?\d{3,5})?|\d+GB|\d{3,5}(?:MHZ|MGH)?)$',
    re.IGNORECASE,
)


def extract_part_number(name):
    candidates = []
    for token in PART_NUMBER_RE.findall(name):
        if PART_NUMBER_STOP_RE.match(token):
            continue
        if not (re.search(r'[A-Za-z]', token) and re.search(r'\d', token)):
            continue
        candidates.append(token)

    if not candidates:
        return None
    return max(candidates, key=len).upper()


def migrate_products(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    RAMModule = apps.get_model('products', 'RAMModule')
    Offer = apps.get_model('products', 'Offer')
    PriceSnapshot = apps.get_model('products', 'PriceSnapshot')

    for product in Product.objects.all():
        part_number = extract_part_number(product.name)

        if part_number:
            ram_module, _ = RAMModule.objects.get_or_create(
                part_number=part_number,
                defaults={
                    'name': product.name,
                    'brand': product.brand,
                    'capacity_gb': product.capacity_gb,
                    'memory_type': product.memory_type,
                    'frequency_mhz': product.frequency_mhz,
                },
            )
        else:
            ram_module = RAMModule.objects.create(
                name=product.name,
                brand=product.brand,
                part_number=None,
                capacity_gb=product.capacity_gb,
                memory_type=product.memory_type,
                frequency_mhz=product.frequency_mhz,
            )

        offer = Offer.objects.create(
            ram_module=ram_module,
            marketplace=product.marketplace,
            external_id=product.external_id,
            name=product.name,
            url=product.url,
        )

        PriceSnapshot.objects.filter(product=product).update(offer=offer)


def reverse_noop(apps, schema_editor):
    # Обратная миграция не поддерживается: RAMModule/Offer удаляются
    # структурной миграцией 0005.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_ramodule_offer'),
    ]

    operations = [
        migrations.RunPython(migrate_products, reverse_noop),
    ]
