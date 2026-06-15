from django.db import migrations

MARKETPLACES = [
    {'name': 'DNS', 'url': 'https://www.dns-shop.ru/'},
    {'name': 'MVideo', 'url': 'https://www.mvideo.ru/'},
    {'name': 'Regard', 'url': 'https://www.regard.ru/'},
    {'name': 'Onlinetrade', 'url': 'https://www.onlinetrade.ru/'},
    {'name': 'Citilink', 'url': 'https://www.citilink.ru/'},
]


def create_marketplaces(apps, schema_editor):
    Marketplace = apps.get_model('products', 'Marketplace')
    for item in MARKETPLACES:
        Marketplace.objects.get_or_create(name=item['name'], defaults={'url': item['url']})


def remove_marketplaces(apps, schema_editor):
    Marketplace = apps.get_model('products', 'Marketplace')
    Marketplace.objects.filter(name__in=[item['name'] for item in MARKETPLACES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_marketplaces, remove_marketplaces),
    ]
