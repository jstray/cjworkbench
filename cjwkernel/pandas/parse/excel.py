from pathlib import Path
import pandas as pd
import xlrd
from cjwkernel.types import I18nMessage, RenderError, RenderResult
from ..types import ProcessResult
from ..moduleutils import autocast_dtypes_in_place


def parse_xls_file(
    path: Path, *, output_path: Path, has_header: bool, autoconvert_types: bool
) -> RenderResult:
    """
    Build a RenderResult from xlsx bytes or raise parse error.

    Peculiarities:

    * Error can be xlrd.XLRDError or pandas error
    * We read the entire file contents into memory before parsing
    """
    # Use xlrd.open_workbook(): if we call pandas.read_excel(bytesio) it
    # will read the entire file into RAM.

    # dtype='category' crashes as of 2018-09-11
    try:
        workbook = xlrd.open_workbook(path.as_posix())
        table = pd.read_excel(
            workbook, engine="xlrd", dtype=object, header=(0 if has_header else None)
        )
    except xlrd.XLRDError as err:
        return RenderResult(
            errors=[
                RenderError(
                    I18nMessage.TODO_i18n(f"Error reading Excel file: %s" % str(err))
                )
            ]
        )

    if has_header:
        table.columns = [str(c) for c in table.columns]
    else:
        table.columns = [f"Column {i + 1}" for i in range(len(table.columns))]
    autocast_dtypes_in_place(table)

    return ProcessResult(table).to_arrow(output_path)


parse_xlsx_file = parse_xls_file