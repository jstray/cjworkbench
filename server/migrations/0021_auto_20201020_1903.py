# Generated by Django 2.2.16 on 2020-10-20 19:03

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("server", "0020_set_delta_command_name"),
    ]

    operations = [
        migrations.DeleteModel(
            name="AddModuleCommand",
        ),
        migrations.DeleteModel(
            name="AddTabCommand",
        ),
        migrations.DeleteModel(
            name="ChangeDataVersionCommand",
        ),
        migrations.DeleteModel(
            name="ChangeParametersCommand",
        ),
        migrations.DeleteModel(
            name="ChangeStepNotesCommand",
        ),
        migrations.DeleteModel(
            name="ChangeWorkflowTitleCommand",
        ),
        migrations.DeleteModel(
            name="DeleteModuleCommand",
        ),
        migrations.DeleteModel(
            name="DeleteTabCommand",
        ),
        migrations.DeleteModel(
            name="DuplicateTabCommand",
        ),
        migrations.DeleteModel(
            name="InitWorkflowCommand",
        ),
        migrations.DeleteModel(
            name="ReorderModulesCommand",
        ),
        migrations.DeleteModel(
            name="ReorderTabsCommand",
        ),
        migrations.DeleteModel(
            name="SetTabNameCommand",
        ),
        migrations.AlterModelOptions(
            name="delta",
            options={"ordering": ["id"]},
        ),
        migrations.RemoveField(
            model_name="delta",
            name="polymorphic_ctype",
        ),
    ]
