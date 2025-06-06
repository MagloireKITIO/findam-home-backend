# Generated by Django 4.2.7 on 2025-05-06 09:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('properties', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='property',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=9, max_digits=12, null=True, verbose_name='latitude'),
        ),
        migrations.AlterField(
            model_name='property',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=9, max_digits=12, null=True, verbose_name='longitude'),
        ),
    ]
