# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-05-28 13:37
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0008_auto_20190523_2128'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='aclentry',
            options={'ordering': ['email']},
        ),
    ]
