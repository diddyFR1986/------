import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0002_initial_marketplaces'),
    ]

    operations = [
        migrations.CreateModel(
            name='RAMModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Название')),
                ('brand', models.CharField(max_length=100, verbose_name='Бренд')),
                ('part_number', models.CharField(blank=True, max_length=100, null=True, unique=True, verbose_name='Артикул')),
                ('capacity_gb', models.IntegerField(verbose_name='Объём, ГБ')),
                ('memory_type', models.CharField(blank=True, choices=[('DDR4', 'DDR4'), ('DDR5', 'DDR5')], max_length=10, verbose_name='Тип памяти')),
                ('frequency_mhz', models.IntegerField(blank=True, null=True, verbose_name='Частота, МГц')),
            ],
            options={
                'verbose_name': 'Модуль ОЗУ',
                'verbose_name_plural': 'Модули ОЗУ',
            },
        ),
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=100, verbose_name='ID товара на площадке')),
                ('name', models.CharField(max_length=255, verbose_name='Название')),
                ('url', models.URLField(verbose_name='Ссылка на товар')),
                ('last_updated', models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')),
                ('marketplace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='products.marketplace', verbose_name='Площадка')),
                ('ram_module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='products.rammodule', verbose_name='Модуль ОЗУ')),
            ],
            options={
                'verbose_name': 'Предложение',
                'verbose_name_plural': 'Предложения',
                'unique_together': {('marketplace', 'external_id')},
            },
        ),
        migrations.AddField(
            model_name='pricesnapshot',
            name='offer',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='snapshots', to='products.offer', verbose_name='Предложение'),
        ),
    ]
