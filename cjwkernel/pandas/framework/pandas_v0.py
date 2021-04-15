import asyncio
import inspect
from pathlib import Path
from typing import Any, Dict, Callable, List

import pandas as pd
import cjwparquet
import cjwpandasmodule
import cjwpandasmodule.convert

from cjwkernel import settings, types
from cjwkernel.pandas import types as ptypes
from cjwkernel.pandas.types import arrow_schema_to_render_columns
from cjwkernel.thrift import ttypes
from cjwkernel.types import (
    arrow_render_error_to_thrift,
    arrow_render_result_to_thrift,
    thrift_params_to_arrow,
    thrift_raw_params_to_arrow,
    thrift_render_error_to_arrow,
)
from cjwkernel.util import tempfile_context
from cjwkernel.validate import load_trusted_arrow_file, read_columns


def _arrow_tab_output_to_pandas(
    tab_output: types.TabOutput, basedir: Path
) -> ptypes.TabOutput:
    table = load_trusted_arrow_file(basedir / tab_output.table_filename)
    render_columns = arrow_schema_to_render_columns(table.schema)
    return ptypes.TabOutput(
        tab_output.tab.slug,
        tab_output.tab.name,
        render_columns,
        cjwpandasmodule.convert.arrow_table_to_pandas_dataframe(table),
    )


def _parquet_to_pandas(path: Path) -> pd.DataFrame:
    if path.stat().st_size == 0:
        return pd.DataFrame()
    else:
        with cjwparquet.open_as_mmapped_arrow(path) as arrow_table:
            return arrow_table.to_pandas(
                date_as_object=False,
                deduplicate_objects=True,
                ignore_metadata=True,
                categories=[
                    column_name.encode("utf-8")
                    for column_name, column in zip(
                        arrow_table.column_names, arrow_table.columns
                    )
                    if hasattr(column.type, "dictionary")
                ],
            )  # TODO ensure dictionaries stay dictionaries


def __find_tab_outputs(value: Dict[str, Any]) -> List[types.TabOutput]:
    """Find all `TabOutput` objects in the param dict, `values`."""
    agg: Dict[str, types.TabOutput] = {}  # slug => TabOutput

    def _find_nested(child: Any) -> None:
        if isinstance(child, types.TabOutput):
            nonlocal agg
            agg[child.tab.slug] = child
        elif isinstance(child, dict):
            for grandchild in child.values():
                _find_nested(grandchild)
        elif isinstance(child, list):
            for grandchild in child:
                _find_nested(grandchild)

    _find_nested(value)

    return list(agg.values())


def call_render(render: Callable, request: ttypes.RenderRequest) -> ttypes.RenderResult:
    basedir = Path(request.basedir)
    input_path = basedir / request.input_filename
    table = load_trusted_arrow_file(input_path)
    dataframe = cjwpandasmodule.convert.arrow_table_to_pandas_dataframe(table)
    params = _arrow_param_to_pandas_param(
        thrift_params_to_arrow(request.params, basedir).params, basedir
    )

    spec = inspect.getfullargspec(render)
    kwargs = {}
    varkw = bool(spec.varkw)  # if True, function accepts **kwargs
    kwonlyargs = spec.kwonlyargs
    if varkw or "fetch_result" in kwonlyargs:
        if request.fetch_result is None:
            fetch_result = None
        else:
            fetch_result_path = basedir / request.fetch_result.filename
            errors = [
                thrift_render_error_to_arrow(e) for e in request.fetch_result.errors
            ]
            if (
                fetch_result_path.stat().st_size == 0
                or cjwparquet.file_has_parquet_magic_number(fetch_result_path)
            ):
                fetch_result = ptypes.ProcessResult(
                    dataframe=_parquet_to_pandas(fetch_result_path),
                    errors=errors,
                    # infer columns -- the fetch interface doesn't handle formats
                    # (TODO nix pandas_v0 fetching altogether by rewriting all modules)
                )
            else:
                # TODO nix pandas Fetch modules. (Do any use files, even?)
                fetch_result = types.FetchResult(path=fetch_result_path, errors=errors)
        kwargs["fetch_result"] = fetch_result
    if varkw or "settings" in kwonlyargs:
        kwargs["settings"] = settings
    if varkw or "tab_name" in kwonlyargs:
        kwargs["tab_name"] = request.tab.name
    if varkw or "input_columns" in kwonlyargs:
        kwargs["input_columns"] = arrow_schema_to_render_columns(table.schema)

    input_columns = read_columns(table, full=False)
    raw_result = render(dataframe, params, **kwargs)

    # raise ValueError if invalid
    pandas_result = ptypes.ProcessResult.coerce(
        raw_result, try_fallback_columns=input_columns
    )
    pandas_result.truncate_in_place_if_too_big()

    arrow_result = pandas_result.to_arrow(basedir / request.output_filename)
    return arrow_render_result_to_thrift(arrow_result)


def _arrow_param_to_pandas_param(param: Any, basedir: Path):
    """Recursively prepare `params` to be passed to `render()`.

    * TabOutput gets converted so it has dataframe.
    """
    if isinstance(param, list):
        return [_arrow_param_to_pandas_param(p, basedir) for p in param]
    elif isinstance(param, dict):
        return {k: _arrow_param_to_pandas_param(v, basedir) for k, v in param.items()}
    elif isinstance(param, types.TabOutput):
        return _arrow_tab_output_to_pandas(param, basedir)
    else:
        return param


def call_fetch(fetch: Callable, request: ttypes.FetchRequest) -> ttypes.FetchResult:
    """Call `fetch()` and validate the result.

    Module code may contain errors. This function and `fetch()` should strive
    to raise developer-friendly errors in the case of bugs -- including
    unexpected input.
    """
    # thrift => pandas
    basedir = Path(request.basedir)
    params: Dict[str, Any] = _arrow_param_to_pandas_param(
        thrift_params_to_arrow(request.params, basedir).params, basedir
    )
    output_path = basedir / request.output_filename

    spec = inspect.getfullargspec(fetch)
    kwargs = {}
    varkw = bool(spec.varkw)  # if True, function accepts **kwargs
    kwonlyargs = spec.kwonlyargs

    if varkw or "secrets" in kwonlyargs:
        kwargs["secrets"] = thrift_raw_params_to_arrow(request.secrets).params
    if varkw or "settings" in kwonlyargs:
        kwargs["settings"] = settings
    if varkw or "get_input_dataframe" in kwonlyargs:

        async def get_input_dataframe():
            if request.input_table_parquet_filename is None:
                return None
            else:
                return _parquet_to_pandas(
                    basedir / request.input_table_parquet_filename
                )

        kwargs["get_input_dataframe"] = get_input_dataframe

    if varkw or "output_path" in kwonlyargs:
        kwargs["output_path"] = output_path

    result = fetch(params, **kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)

    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], Path):
        errors = ptypes.coerce_RenderError_list(result[1])
    elif isinstance(result, Path):
        errors = []
    elif isinstance(result, list):
        errors = ptypes.coerce_RenderError_list(result)
    else:
        pandas_result = ptypes.ProcessResult.coerce(result)
        pandas_result.truncate_in_place_if_too_big()
        # ProcessResult => FetchResult isn't a thing; but we can hack it using
        # ProcessResult => RenderResult => FetchResult.
        with tempfile_context(suffix=".arrow") as arrow_path:
            if pandas_result.columns:
                hacky_result = pandas_result.to_arrow(arrow_path)
                table = load_trusted_arrow_file(arrow_path)
                cjwparquet.write(output_path, table)
                errors = hacky_result.errors
            else:
                output_path.write_bytes(b"")
                errors = pandas_result.errors

    return ttypes.FetchResult(
        filename=request.output_filename,
        errors=[arrow_render_error_to_thrift(e) for e in errors],
    )
