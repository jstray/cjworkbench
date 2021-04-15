import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pyarrow as pa
import pyarrow.compute
from cjwmodule.arrow.format import parse_number_format

from .types import Column, ColumnType
from . import settings


class ValidateError(ValueError):
    """Arrow table and metadata do not meet Workbench's requirements."""


class InvalidArrowFile(ValidateError):
    """arrow-validate of a path failed.

    Run arrow-validate before opening an Arrow file in Python, for SECURITY.
    """

    def __init__(self, text):
        super().__init__("arrow-validate: " + text)


class TableSchemaHasMetadata(ValidateError):
    def __init__(self):
        super().__init__("table.schema.metadata must be None; got non-null")


class TableHasTooManyRecordBatches(ValidateError):
    def __init__(self, actual: int):
        super().__init__("Table has %d record batches; we only support 1" % actual)


class DuplicateColumnName(ValidateError):
    def __init__(self, name: str, position1: int, position2: int):
        super().__init__(
            "Table has two columns named '%s': column %d and column %d"
            % (name, position1, position2)
        )


class FieldMetadataNotAllowed(ValidateError):
    def __init__(self, name: str, wanted: str, metadata: Dict[bytes, bytes]):
        super().__init__(
            "Table column '%s' has invalid metadata: wanted %s; got %r"
            % (name, wanted, metadata)
        )


class WrongColumnType(ValidateError):
    def __init__(self, name: str, type: pa.DataType):
        super().__init__(
            "Table column '%s' has invalid type: expected timestamp/utf8/integer/floating/date32, got %r"
            % (name, type)
        )


class TimestampTimezoneNotAllowed(ValidateError):
    def __init__(self, name: str, dtype: pa.TimestampType):
        super().__init__(
            "Table column '%s' (%r) has a time zone, but Workbench does not support time zones"
            % (name, dtype)
        )


class DateMetadataNotAllowed(ValidateError):
    def __init__(self, name: str, metadata: Dict[bytes, bytes]):
        super().__init__(
            "Table column '%s' has type date, so field.metadata should have b'unit' of day, week, month, quarter or year; got %r"
            % (name, metadata)
        )


class TimestampUnitNotAllowed(ValidateError):
    def __init__(self, name: str, dtype: pa.TimestampType):
        super().__init__(
            "Table column '%s' (%r) has unit '%s', but Workbench only supports 'ns'"
            % (name, dtype, dtype.unit)
        )


class DateOutOfRange(ValidateError):
    def __init__(self, name: str):
        super().__init__(
            "Table column %r has invalid value(s): the valid range is 0001-01-01 - 9999-12-31."
            % (name,)
        )


class DateValueHasWrongUnit(ValidateError):
    def __init__(self, name: str, unit: str):
        super().__init__(
            "Table column %r has invalid value: every date must be the first day of a %r"
            % (name, unit)
        )


class InvalidNumberFormat(ValidateError):
    def __init__(self, name: str, format: str):
        super().__init__(
            "Table column %r has invalid number format: %r" % (name, format)
        )


def validate_arrow_file(path: Path) -> None:
    """Validate that `table` can be loaded at all.

    Raise InvalidArrowFile if:

    * The file is empty or has no Arrow header
    * Text columns' offsets are invalid
    * A column name has invalid UTF-8
    * A column name is too long (see settings.MAX_BYTES_PER_COLUMN_NAME)
    * A column name contains ASCII control characters (a newline, for example)
    * Some text data has invalid UTF-8
    * A float is NaN or Infinity.
    * A dictionary column's dictionary contains nulls or unused values
    """
    try:
        subprocess.run(
            [
                "/usr/bin/arrow-validate",
                "--check-column-name-control-characters",
                f"--check-column-name-max-bytes={settings.MAX_BYTES_PER_COLUMN_NAME}",
                "--check-dictionary-values-all-used",
                "--check-dictionary-values-not-null",
                "--check-dictionary-values-unique",
                "--check-floats-all-finite",
                "--check-safe",
                path.as_posix(),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as err:
        message = err.stdout[:-1]  # strip trailing "\n"
        raise InvalidArrowFile(message) from None


def _read_column_type(
    column: pa.ChunkedArray, field: pa.Field, *, full: bool
) -> ColumnType:
    """Read ColumnType from metadata, or raise ValidateError.

    If `full=False`, skip costly checks. Only pass `full=False` when you can
    guarantee the data has been generated by a source you trust. (In particular,
    module output is not trusted and it must use the default `full=True`.)
    """
    if pa.types.is_timestamp(field.type):
        if field.metadata is not None:
            raise FieldMetadataNotAllowed(field.name, "None", field.metadata)
        if field.type.tz is not None:
            raise TimestampTimezoneNotAllowed(field.name, column.type)
        if field.type.unit != "ns":
            raise TimestampUnitNotAllowed(field.name, column.type)
        return ColumnType.Timestamp()

    if pa.types.is_date32(field.type):
        if (
            field.metadata is None
            or len(field.metadata) != 1
            or (
                field.metadata.get(b"unit")
                not in {b"day", b"week", b"month", b"quarter", b"year"}
            )
        ):
            raise FieldMetadataNotAllowed(
                field.name, "'unit' of day/week/month/quarter/year", field.metadata
            )
        unit = field.metadata[b"unit"].decode("ascii")
        if full:
            if unit == "day":
                pass
            elif unit == "week":
                # Only Mondays (ISO weekday = 0) are valid
                for chunk in column.chunks:
                    # 1970-01-01 (date32=0) was Thursday. Shift such that
                    # date32=0 is Monday. If chunk == -3, monday0_i64 == 0.
                    #
                    # We use i64 to avoid overflow
                    monday0_i64 = pa.compute.add(
                        chunk.view(pa.int32()).cast(pa.int64()), 3
                    )
                    # divide+multiply. For each date in monday0_i64,
                    # all_mondays will be the monday of that week
                    all_mondays = pa.compute.multiply(
                        pa.compute.divide(monday0_i64, 7), 7
                    )
                    if pa.compute.any(
                        pa.compute.not_equal(monday0_i64, all_mondays)
                    ).as_py():
                        raise DateValueHasWrongUnit(field.name, "week")
                return ColumnType.Date(unit="week")
            else:
                is_valid = {
                    "month": lambda st: st.tm_mday == 1,
                    "quarter": lambda st: st.tm_mday == 1 and st.tm_mon % 3 == 1,
                    "year": lambda st: st.tm_mon == 1 and st.tm_mday == 1,
                }[unit]
                for chunk in column.chunks:
                    unix_timestamps = pa.compute.multiply(
                        chunk.view(pa.int32()).cast(pa.int64()), 86400
                    )
                    for unix_timestamp in unix_timestamps:
                        if unix_timestamp.is_valid:
                            struct_time = time.gmtime(unix_timestamp.as_py())
                            if not is_valid(struct_time):
                                raise DateValueHasWrongUnit(field.name, unit)

        return ColumnType.Date(unit=unit)

    if pa.types.is_string(field.type) or (
        pa.types.is_dictionary(field.type)
        and pa.types.is_integer(field.type.index_type)
    ):
        if field.metadata is not None:
            raise FieldMetadataNotAllowed(field.name, "None", field.metadata)
        return ColumnType.Text()

    if pa.types.is_integer(field.type) or pa.types.is_floating(field.type):
        if (
            field.metadata is None
            or len(field.metadata) != 1
            or b"format" not in field.metadata
        ):
            raise FieldMetadataNotAllowed(
                field.name, "'format' in metadata", field.metadata
            )

        try:
            format = field.metadata[b"format"].decode("utf-8")
        except ValueError:
            raise InvalidNumberFormat(
                field.name, field.metadata[b"format"].decode("latin1")
            )

        try:
            parse_number_format(format)
        except ValueError:
            raise InvalidNumberFormat(field.name, format)

        return ColumnType.Number(format=format)

    raise WrongColumnType(field.name, field.type)


def read_columns(table: pa.Table, full: bool = True) -> List[Column]:
    """Read Column definitions and validate Workbench assumptions.

    Raise ValidateError if:

    * table has metadata
    * table has more than one record batch
    * columns have invalid metadata (e.g., a "format" on a "text" column, or
      a timestamp with unit!=ns or a timezone)
    * column values disagree with metadata (e.g., date32 "2021-04-12" with
      `ColumnType.Date("month")`)

    Be sure the Arrow file backing the table was validated with
    `validate_arrow_file()` first. Otherwise, you'll get undefined behavior.

    If `full=False`, skip costly checks. Only pass `full=False` when you can
    guarantee the data has been generated by a source you trust. (In particular,
    module output is not trusted and it must use the default `full=True`.)
    """
    if table.schema.metadata is not None:
        raise TableSchemaHasMetadata()

    seen_column_names: Dict[str, int] = {}
    ret = []

    for position, column in enumerate(table.itercolumns()):
        field = table.field(position)
        if column.num_chunks > 1:
            raise TableHasTooManyRecordBatches(column.num_chunks)

        if field.name in seen_column_names:
            raise DuplicateColumnName(
                field.name, seen_column_names[field.name], position
            )
        else:
            seen_column_names[field.name] = position

        ret.append(Column(field.name, _read_column_type(column, field, full=full)))

    return ret


def load_untrusted_arrow_file_with_columns(path: Path) -> Tuple[pa.Table, List[Column]]:
    """Load Arrow file from an untrusted source.

    Raise ValidateError if the file is a security risk (e.g., has invalid
    buffer offsets) or if its data is wrong (invalid UTF-8; out-of-range date32
    values; bad number formats; invalid metadata).

    Use this to load modules' outputs. If loading succeeds, you can now "trust"
    the Arrow file at `path`.
    """
    validate_arrow_file(path)  # raise ValidateError

    # Validate passed, so it's safe to open the Arrow file ... and the read will
    # not fail.
    reader = pyarrow.ipc.open_file(path)
    table = reader.read_all()

    columns = read_columns(table, full=True)  # raise ValidateError

    return table, columns


def load_trusted_arrow_file(path: Path) -> pa.Table:
    """Load Arrow file from a trusted source.

    Don't raise any errors. Assume the Arrow file was validated already.
    """
    reader = pyarrow.ipc.open_file(path)
    table = reader.read_all()
    return table


def load_trusted_arrow_file_with_columns(path: Path) -> Tuple[pa.Table, List[Column]]:
    table = load_trusted_arrow_file(path)
    columns = read_columns(table, full=False)

    return table, columns
