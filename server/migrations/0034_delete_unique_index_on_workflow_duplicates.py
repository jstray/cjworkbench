# Generated by Django 3.1.6 on 2021-02-04 20:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("server", "0033_auto_20210202_1848"),
    ]

    operations = [
        migrations.RunSQL(["DROP INDEX IF EXISTS unique_workflow_copy_by_user"])
    ]
