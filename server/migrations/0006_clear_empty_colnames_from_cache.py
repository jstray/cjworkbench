# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-05-07 18:25
from __future__ import unicode_literals

from django.db import migrations


def clear_empty_colnames_from_cache(apps, schema_editor):
    # Can't grab WfModule from 'apps' because we need our migration to write to
    # S3 -- which 'apps' models don't.
    from cjwstate.rendercache.io import clear_cached_render_result_for_wf_module
    from server.models import WfModule

    qs = WfModule.objects.extra(
        # Lots of escaping here: '\"' gets us double quotes; '%%' gives SQL '%'
        # instead of the DB module's SQL param replacement.
        where=['cached_render_result_columns::text LIKE \'%%"name": ""%%\'']
        # also, set ".only" so we don't select columns created in later migrations
    ).only(
        "id",
        "tab_id",
        "cached_render_result_delta_id",
        "cached_render_result_status",
        "cached_render_result_error",
        "cached_render_result_json",
        "cached_render_result_quick_fixes",
        "cached_render_result_columns",
        "cached_render_result_nrows",
    )
    for wf_module in qs:
        with wf_module.workflow.cooperative_lock():
            clear_cached_render_result_for_wf_module(wf_module)


class Migration(migrations.Migration):
    """
    Delete cached results that have empty column names.

    Prior to https://www.pivotaltracker.com/story/show/162648330, there was no
    check in place to prevent empty columns from existing. We have since
    modified every module that creates columns to ensure it never outputs an
    empty column name. This migration "fixes" all the "pass-thru" modules that
    don't modify input column names: to ensure their _output_ valid, we need to
    ensure their _input_ is valid. That means running the modules that produce
    their input.

    Clear all cache results with empty column names.
    """

    dependencies = [("server", "0005_unique_implicit_duplicate_workflows")]

    operations = [migrations.RunPython(clear_empty_colnames_from_cache, elidable=True)]
