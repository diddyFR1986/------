import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0004_migrate_products_to_offers'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pricesnapshot',
            name='product',
        ),
        migrations.AlterField(
            model_name='pricesnapshot',
            name='offer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='snapshots', to='products.offer', verbose_name='Предложение'),
        ),
        migrations.DeleteModel(
            name='Product',
        ),
    ]
