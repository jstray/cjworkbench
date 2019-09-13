from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import json
import marshal
from pathlib import Path
import pyarrow
import pyarrow.ipc
import pyarrow.types
from string import Formatter
from typing import Any, Dict, List, Optional, Union
from cjwkernel.util import json_encode

# Some types we can import with no conversion
from .thrift import ttypes

__all__ = [
    "ArrowTable",
    "Column",
    "ColumnType",
    "CompiledModule",
    "I18nMessage",
    "Params",
    "QuickFix",
    "QuickFixAction",
    "RenderError",
    "RenderResult",
    "Tab",
    "TableMetadata",
    "TabOutput",
]


@dataclass(frozen=True)
class CompiledModule:
    module_slug: str
    """
    Identifier for the module.

    This helps with log messages and debugging.
    """

    marshalled_code_object: bytes
    """
    `compile()` return value, serialied by "marshal" module.

    This can be used as: `exec(marshal.loads(marshalled_code_object))`.

    (The "marshal" module is designed specifically for building pyc files;
    that's the way we use it.)
    """

    @property
    def code_object(self) -> Any:
        return marshal.loads(self.marshalled_code_object)


class ColumnType(ABC):
    """
    Data type of a column.

    This describes how it is presented -- not how its bytes are arranged.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The name of the type: 'text', 'number' or 'datetime'.
        """
        pass

    @abstractmethod
    def to_thrift(self) -> ttypes.ColumnType:
        """
        Build a Thrift representation of this type.
        """
        pass

    @classmethod
    def from_thrift(cls, value: ttypes.ColumnType) -> ColumnType:
        if value.text_type is not None:
            return cls.Text()
        elif value.number_type is not None:
            format = value.number_type.format
            NumberFormatter(format)  # raise ValueError on invalid format
            return cls.Number(format)
        elif value.datetime_type is not None:
            return cls.Datetime()
        else:
            raise ValueError("Unhandled Thrift object: %r" % value)


@dataclass(frozen=True)
class ColumnTypeText(ColumnType):
    # override
    @property
    def name(self) -> str:
        return "text"

    # override
    def to_thrift(self) -> ttypes.ColumnType:
        return ttypes.ColumnType(text_type=ttypes.ColumnTypeText())


class NumberFormatter:
    """
    Utility to convert int and float to str.

    Usage:

        formatter = NumberFormatter('${:,.2f}')
        formatter.format(1234.56)  # => "$1,234.56"

    This is similar to Python `format()` but different:

    * It allows formatting float as int: `NumberFormatter('{:d}').format(0.1)`
    * It disallows "conversions" (e.g., `{!r:s}`)
    * It disallows variable name/numbers (e.g., `{1:d}`, `{value:d}`)
    * It raises ValueError on construction if format is imperfect
    * Its `.format()` method always succeeds
    """

    _IntTypeSpecifiers = set("bcdoxXn")
    """
    Type names that operate on integer (as opposed to float).

    Python `format()` auto-converts int to float, but it doesn't auto-convert
    float to int. Workbench does auto-convert float to int: any format that
    works for one Number must work for all Numbers.
    """

    def __init__(self, format_s: str):
        if not isinstance(format_s, str):
            raise ValueError("Format must be str")

        # parts: a list of (literal_text, field_name, format_spec, conversion)
        #
        # The "literal_text" always comes _before_ the field. So we end up
        # with three possibilities:
        #
        #    "prefix{}suffix": [(prefix, "", "", ""), (suffix, None...)]
        #    "prefix{}": [(prefix, "", "", '")]
        #    "{}suffix": [("", "", "", ""), (suffix, None...)]
        parts = list(Formatter().parse(format_s))

        if len(parts) > 2 or len(parts) == 2 and parts[1][1] is not None:
            raise ValueError("Can only format one number")

        if not parts or parts[0][1] is None:
            raise ValueError('Format must look like "{:...}"')

        if parts[0][1] != "":
            raise ValueError("Field names or numbers are not allowed")

        if parts[0][3] is not None:
            raise ValueError("Field converters are not allowed")

        self._prefix = parts[0][0]
        self._format_spec = parts[0][2]
        if len(parts) == 2:
            self._suffix = parts[1][0]
        else:
            self._suffix = ""
        self._need_int = (
            self._format_spec and self._format_spec[-1] in self._IntTypeSpecifiers
        )

        # Test it!
        #
        # A reading of cpython 3.7 Python/formatter_unicode.c
        # parse_internal_render_format_spec() suggests the following unobvious
        # details:
        #
        # * Python won't parse a format spec unless you're formatting a number
        # * _PyLong_FormatAdvancedWriter() accepts a superset of the formats
        #   _PyFloat_FormatAdvancedWriter() accepts. (Workbench accepts that
        #   superset.)
        #
        # Therefore, if we can format an int, the format is valid.
        format(1, self._format_spec)

    def format(self, value: Union[int, float]) -> str:
        if self._need_int:
            value = int(value)
        else:
            # Format float64 _integers_ as int. For instance, '3.0' should be
            # formatted as though it were the int, '3'.
            #
            # Python would normally format '3.0' as '3.0' by default; that's
            # not acceptable to us because we can't write a JavaScript
            # formatter that would do the same thing. (Javascript doesn't
            # distinguish between float and int.)
            int_value = int(value)
            if int_value == value:
                value = int_value

        return self._prefix + format(value, self._format_spec) + self._suffix


@dataclass(frozen=True)
class ColumnTypeNumber(ColumnType):
    # https://docs.python.org/3/library/string.html#format-specification-mini-language
    format: str = "{:,}"  # Python format() string -- default adds commas
    # TODO handle locale, too: format depends on it. Python will make this
    # difficult because it can't format a string in an arbitrary locale: it can
    # only do it using global variables, which we can't use.

    def __post_init__(self):
        formatter = NumberFormatter(self.format)  # raises ValueError
        object.__setattr__(self, "_formatter", formatter)

    # override
    @property
    def name(self) -> str:
        return "number"

    # override
    def to_thrift(self) -> ttypes.ColumnType:
        return ttypes.ColumnType(number_type=ttypes.ColumnTypeNumber(self.format))


@dataclass(frozen=True)
class ColumnTypeDatetime(ColumnType):
    # # https://docs.python.org/3/library/datetime.html#strftime-strptime-behavior
    # format: str = '{}'  # Python format() string

    # # TODO handle locale, too: format depends on it. Python will make this
    # # difficult because it can't format a string in an arbitrary locale: it can
    # # only do it using global variables, which we can't use.

    # override
    @property
    def name(self) -> str:
        return "datetime"

    # override
    def to_thrift(self) -> ttypes.ColumnType:
        return ttypes.ColumnType(datetime_type=ttypes.ColumnTypeDatetime())


# Aliases to help with import. e.g.:
# from cjwkernel.pandas.types import Column, ColumnType
# column = Column('A', ColumnType.Number('{:,.2f}'))
ColumnType.Text = ColumnTypeText
ColumnType.Number = ColumnTypeNumber
ColumnType.Datetime = ColumnTypeDatetime

ColumnType.TypeLookup = {
    "text": ColumnType.Text,
    "number": ColumnType.Number,
    "datetime": ColumnType.Datetime,
}


@dataclass(frozen=True)
class Column:
    """
    A column definition.
    """

    name: str  # Name of the column
    type: ColumnType  # How it's displayed

    def to_dict(self):
        return {"name": self.name, "type": self.type.name, **asdict(self.type)}

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> Column:
        return cls.from_kwargs(**d)

    @classmethod
    def from_kwargs(cls, name: str, type: str, **column_type_kwargs) -> ColumnType:
        type_cls = ColumnType.TypeLookup[type]
        return cls(name, type_cls(**column_type_kwargs))

    @classmethod
    def from_thrift(cls, value: ttypes.Column) -> Column:
        return cls(value.name, ColumnType.from_thrift(value.type))

    def to_thrift(self) -> ttypes.Column:
        return ttypes.Column(self.name, self.type.to_thrift())


@dataclass(frozen=True)
class TableMetadata:
    """Table data that will be cached for easy access."""

    n_rows: int = 0
    """Number of rows in the table."""

    columns: List[Column] = field(default_factory=list)
    """Columns -- the user-visible aspects of them, at least."""

    @classmethod
    def from_thrift(cls, value: ttypes.TableMetadata) -> TableMetadata:
        return cls(value.n_rows, [Column.from_thrift(c) for c in value.columns])

    def to_thrift(self) -> ttypes.TableMetadata:
        return ttypes.TableMetadata(self.n_rows, [c.to_thrift() for c in self.columns])


@dataclass(frozen=True)
class ArrowTable:
    """
    Table on disk, opened and mmapped.

    A table with no rows must have a file on disk. A table with no _columns_
    is a special case: it must have `table is None and path is None`.

    `self.table` will be populated and validated during construction.

    To pass an ArrowTable between processes, the file must be readable at the
    same `path` to both processes. If your ArrowTable isn't being shared
    between processes, you may safely delete the file at `path` immediately
    after constructing the ArrowTable.
    """

    path: Optional[Path] = None
    """
    Name of file on disk that contains data.

    If and only if the table has columns, the file must exist.
    """

    metadata: TableMetadata = field(default_factory=TableMetadata)
    """Metadata; must agree with `table`."""

    def __post_init__(self):
        """
        Open the file on disk with mmap().

        Raise OSError if file on disk could not be read.

        Raise AssertionError if file on disk does not match metadata.
        """
        if self.path is None:
            assert len(self.metadata.columns) == 0
            table = None
        if self.path is not None:
            assert len(self.metadata.columns) != 0
            reader = pyarrow.ipc.open_file(str(self.path))
            table = reader.read_all()
            assert table.num_rows == self.metadata.n_rows
            assert table.num_columns == len(self.metadata.columns)
            for tcol, mcol in zip(table.columns, self.metadata.columns):
                assert tcol.name == mcol.name
                # Assert the column type is one we support
                ttype = tcol.type
                assert (
                    pyarrow.types.is_timestamp(ttype)
                    or pyarrow.types.is_floating(ttype)
                    or pyarrow.types.is_integer(ttype)
                    or pyarrow.types.is_string(ttype)
                    or (
                        pyarrow.types.is_dictionary(ttype)
                        and pyarrow.types.is_string(ttype.value_type)
                    )
                )
                # Assert the column type in our metadata matches it
                assert pyarrow.types.is_timestamp(ttype) == isinstance(
                    mcol.type, ColumnTypeDatetime
                )
                assert (
                    pyarrow.types.is_floating(ttype) or pyarrow.types.is_integer(ttype)
                ) == isinstance(mcol.type, ColumnTypeNumber)
                assert (
                    pyarrow.types.is_string(ttype) or pyarrow.types.is_dictionary(ttype)
                ) == isinstance(mcol.type, ColumnTypeText)
        object.__setattr__(self, "table", table)

    def __eq__(self, other: Any) -> bool:
        """
        Compare for table equality: same Arrow data and same metadata.

        `path` is not tested. Typical callers will use tempfiles and not care
        whether they're equal.
        """
        return (
            isinstance(other, type(self))
            and other.metadata == self.metadata
            and (
                (other.table is None and self.table is None)
                or (
                    other.table is not None
                    and self.table is not None
                    and other.table.equals(self.table)
                )
            )
        )

    @property
    def n_bytes_on_disk(self) -> int:
        """
        Return the number of bytes consumed on disk.

        Raise FileNotFoundError if the file on disk could not be read.
        """
        if self.path is None:
            return 0
        else:
            return self.path.stat().st_size

    @classmethod
    def from_thrift(cls, value: ttypes.ArrowTable) -> ArrowTable:
        """
        Convert from a Thrift ArrowTable.

        Raise OSError if the file on disk could not be read.

        Raise AssertionError if the file on disk does not match metadata.
        """
        return cls(
            Path(value.filename) if value.filename else None,
            TableMetadata.from_thrift(value.metadata),
        )

    def to_thrift(self) -> ttypes.ArrowTable:
        return ttypes.ArrowTable(
            "" if self.path is None else str(self.path), self.metadata.to_thrift()
        )


@dataclass(frozen=True)
class Tab:
    """Tab description."""

    slug: str
    """Tab identifier, unique in its Workflow."""

    name: str
    """Tab name, provided by the user."""

    @classmethod
    def from_thrift(cls, value: ttypes.Tab) -> Tab:
        return cls(value.slug, value.name)

    def to_thrift(self) -> ttypes.Tab:
        return ttypes.Tab(self.slug, self.name)


@dataclass(frozen=True)
class TabOutput:
    """
    Already-computed output of a tab.

    During workflow execute, the output from one tab can be used as the input to
    another. This only happens if the output was a `RenderResult` with a
    non-zero-column `table`. (The executor won't run a Step whose inputs aren't
    valid.)
    """

    tab: Tab
    """Tab that was processed."""

    table: ArrowTable
    """
    Output from the final Step in `tab`.

    This is not a RenderResult because the kernel will not render a Step if one
    of its params is a Tab whose result `.status` is not "ok".
    """

    @classmethod
    def from_thrift(cls, value: ttypes.TabOutput) -> TabOutput:
        return cls(value.tab, value.table)

    def to_thrift(self) -> ttypes.TabOutput:
        return ttypes.TabOutput(self.tab, self.table)


def _i18n_argument_from_thrift(value: ttypes.I18nArgument) -> Union[str, int, float]:
    if value.string_value is not None:
        return value.string_value
    elif value.i32_value is not None:
        return value.i32_value
    elif value.double_value is not None:
        return value.double_value
    else:
        raise RuntimeError("Unhandled ttypes.I18nArgument: %r" % value)


def _i18n_argument_to_thrift(value: Union[str, int, float]) -> ttypes.I18nArgument:
    if isinstance(value, str):
        return ttypes.I18nArgument(string_value=value)
    elif isinstance(value, int):
        return ttypes.I18nArgument(i32_value=value)
    elif isinstance(value, float):
        return ttypes.I18nArgument(double_value=value)
    else:
        raise RuntimeError("Unhandled value for I18nArgument: %r" % value)


@dataclass(frozen=True)
class I18nMessage:
    """Translation key and arguments."""

    id: str
    """Message ID. For instance, `modules.renamecolumns.duplicateColname`"""

    args: Dict[str, Union[int, float, str]] = field(default_factory=dict)
    """Arguments (empty if message does not need any -- which is common)."""

    @classmethod
    def from_thrift(cls, value: ttypes.I18nMessage) -> I18nMessage:
        return cls(
            value.id,
            {k: _i18n_argument_from_thrift(v) for k, v in value.arguments.items()},
        )

    def to_thrift(self) -> ttypes.I18nMessage:
        return ttypes.I18nMessage(
            self.id, {k: _i18n_argument_to_thrift(v) for k, v in self.args.items()}
        )

    @classmethod
    def TODO_i18n(cls, text: str) -> I18nMessage:
        """
        Build an I18nMessage that "translates" into English only.

        The message has id "TODO_i18n" and one argument, "text", in English.
        Long-term, all these messages should disappear; but this helps us
        migrate by letting us code without worrying about translation.
        """
        return cls("TODO_i18n", {"text": text})

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> I18nMessage:
        return cls(value["id"], value["arguments"])

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "arguments": self.args}


ParamValue = Optional[
    Union[
        str,
        int,
        float,
        bool,
        Column,
        TabOutput,
        List[Any],  # should be List[ParamValue]
        Dict[str, Any],  # should be Dict[str, ParamValue]
    ]
]


@dataclass(frozen=True)
class RawParams:
    params: Dict[str, Any]

    @classmethod
    def from_thrift(cls, value: ttypes.RawParams) -> RawParams:
        return cls(json.loads(value.json))

    def to_thrift(self) -> ttypes.RawParams:
        return ttypes.RawParams(json_encode(self.params))


@dataclass(frozen=True)
class Params:
    """
    Nested data structure passed to `render()` -- includes Column/TabOutput.
    """

    params: Dict[str, Any]

    @classmethod
    def _value_from_thrift(cls, value: ttypes.ParamValue) -> ParamValue:
        if value.string_value is not None:
            return value.string_value
        elif value.integer_value is not None:
            return value.integer_value
        elif value.float_value is not None:
            return value.float_value
        elif value.boolean_value is not None:
            return value.boolean_value
        elif value.column_value is not None:
            return Column.from_thrift(value.column_value)
        elif value.tab_value is not None:
            return TabOutput.from_thrift(value.tab_value)
        elif value.list_value is not None:
            return [cls._value_from_thrift(v) for v in value.list_value]
        elif value.map_value is not None:
            return {k: cls._value_from_thrift(v) for k, v in value.map_value.items()}
        else:
            return None

    @classmethod
    def _value_to_thrift(cls, value: ParamValue) -> ttypes.ParamValue:
        PV = ttypes.ParamValue

        if value is None:
            return PV()  # a Thrift union with no value
        elif isinstance(value, str):
            # string, file, enum
            return PV(string_value=value)
        elif isinstance(value, int) and not isinstance(value, bool):
            return PV(integer_value=value)
        elif isinstance(value, float):
            return PV(float_value=value)
        elif isinstance(value, bool):
            # boolean, enum
            return PV(boolean_value=value)
        elif isinstance(value, Column):
            return PV(column_value=value.to_thrift())
        elif isinstance(value, TabOutput):
            return PV(tab_value=value.to_thrift())
        elif isinstance(value, list):
            # list, multicolumn, multitab, multichartseries
            return PV(list_value=[cls._value_to_thrift(v) for v in value])
        elif isinstance(value, dict):
            # map, dict
            return PV(map_value={k: cls._value_to_thrift(v) for k, v in value.items()})
        else:
            raise RuntimeError("Unhandled value %r" % value)

    @classmethod
    def from_thrift(cls, value: Dict[str, ttypes.ParamValue]) -> Params:
        return cls({k: cls._value_from_thrift(v) for k, v in value.items()})

    def to_thrift(self) -> Dict[str, ttypes.ParamValue]:
        return {k: self._value_to_thrift(v) for k, v in self.params.items()}


class QuickFixAction(ABC):
    """Instruction for what happens when the user clicks a Quick Fix button."""

    @classmethod
    def from_thrift(cls, value: ttypes.QuickFixAction):
        if value.prepend_step is not None:
            return PrependStepQuickFixAction.from_thrift(value.prepend_step)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]):
        if value["type"] == "prependStep":
            return PrependStepQuickFixAction.from_dict(value)
        else:
            raise ValueError("Unhandled type in QuickFixAction: %r", value)

    @abstractmethod
    def to_thrift(self) -> ttypes.QuickFixAction:
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to Dict.
        
        Subclasses must implement this method. The returned dict must have a
        "type" key, so `QuickFix.from_dict()` can handle it.
        """


@dataclass(frozen=True)
class PrependStepQuickFixAction:
    """Instruction that upon clicking a button, we should create a Step."""

    module_slug: str
    """Module to prepend."""

    partial_params: Dict[str, Any]
    """Some params to set on the new Step (atop the module's defaults)."""

    @classmethod
    def from_thrift(
        cls, value: ttypes.PrependStepQuickFixAction
    ) -> PrependStepQuickFixAction:
        return cls(value.module_slug, json.loads(value.partial_params.json))

    # override
    def to_thrift(self) -> ttypes.QuickFixAction:
        return ttypes.QuickFixAction(
            prepend_step=ttypes.PrependStepQuickFixAction(
                self.module_slug, ttypes.RawParams(json_encode(self.partial_params))
            )
        )

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> PrependStepQuickFixAction:
        return cls(value["moduleSlug"], value["partialParams"])

    # override
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "prependStep",
            "moduleSlug": self.module_slug,
            "partialParams": self.partial_params,
        }


QuickFixAction.PrependStep = PrependStepQuickFixAction


@dataclass(frozen=True)
class QuickFix:
    """Button the user can click in response to an error message."""

    button_text: I18nMessage
    action: QuickFixAction

    @classmethod
    def from_thrift(cls, value: ttypes.QuickFix) -> QuickFix:
        return cls(
            I18nMessage.from_thrift(value.button_text),
            QuickFixAction.from_thrift(value.action),
        )

    def to_thrift(self) -> ttypes.QuickFix:
        return ttypes.QuickFix(self.button_text.to_thrift(), self.action.to_thrift())

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> QuickFix:
        return cls(
            I18nMessage.from_dict(value["buttonText"]),
            QuickFixAction.from_dict(value["action"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "buttonText": self.button_text.to_dict(),
            "action": self.action.to_dict(),
        }


@dataclass(frozen=True)
class RenderError:
    """
    Error or warning encountered during `render()`.

    If `render()` output is a zero-column table, then its result's errors are
    "errors" -- they prevent the workflow from executing. If `render()` outputs
    columns, though, then its result's errors are "warnings" -- execution
    continues and these messages are presented to the user.
    """

    message: I18nMessage
    quick_fixes: List[QuickFix] = field(default_factory=list)

    @classmethod
    def from_thrift(cls, value: ttypes.RenderError) -> RenderError:
        return cls(
            I18nMessage.from_thrift(value.message),
            [QuickFix.from_thrift(qf) for qf in value.quick_fixes],
        )

    def to_thrift(self) -> ttypes.RenderError:
        return ttypes.RenderError(
            self.message.to_thrift(), [qf.to_thrift() for qf in self.quick_fixes]
        )

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> RenderError:
        return cls(
            I18nMessage.from_dict(value["message"]),
            [QuickFix.from_dict(qf) for qf in value["quickFixes"]],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message.to_dict(),
            "quickFixes": [qf.to_dict() for qf in self.quick_fixes],
        }


@dataclass(frozen=True)
class FetchResult:
    """
    The module executed a Step's fetch() without crashing.
    """

    path: Path
    """
    File storing whatever data fetch() output.

    Currently, this is a Parquet file. In the future, it may be something else.
    The file may be empty to indicate a zero-sized table.
    """

    errors: List[RenderError] = field(default_factory=list)
    """
    User-facing errors (or warnings) reported by the module.
    """

    @classmethod
    def from_thrift(cls, value: ttypes.FetchResult) -> FetchResult:
        return cls(
            Path(value.filename), [RenderError.from_thrift(e) for e in value.errors]
        )

    def to_thrift(self) -> ttypes.FetchResult:
        return ttypes.FetchResult(str(self.path), [e.to_thrift() for e in self.errors])


@dataclass(frozen=True)
class RenderResult:
    """
    The module executed a Step's render() without crashing.

    An result may be a user-friendly "error" -- a zero-column table and
    non-empty `errors`. Indeed, Workbench tends to catch and wrap bugs so
    they appear as RenderResult. In a sense, render cannot fail: it will
    _always_ produce a RenderResult.

    To pass a RenderResult between processes, the file must be readable at the
    same `table.path` to both processes. If your RenderResult isn't shared
    between processes, you may safely delete the file at `table.path`
    immediately after constructing `table`.
    """

    table: ArrowTable = field(default_factory=ArrowTable)
    """
    Table the Step outputs.

    If the Step output is "error, then the table must have zero columns.
    """

    errors: List[RenderError] = field(default_factory=list)
    """User-facing errors or warnings reported by the module."""

    json: Dict[str, Any] = field(default_factory=dict)
    """JSON to pass to the module's HTML, if it has HTML."""

    @classmethod
    def from_thrift(cls, value: ttypes.RenderResult) -> RenderResult:
        return cls(
            ArrowTable.from_thrift(value.table),
            [RenderError.from_thrift(e) for e in value.errors],
            json.loads(value.json) if value.json else None,
        )

    @classmethod
    def from_deprecated_error(
        cls, message: str, *, quick_fixes: List[QuickFix] = []
    ) -> RenderError:
        return cls(
            errors=[
                RenderError(I18nMessage("TODO_i18n", {"text": message}), quick_fixes)
            ]
        )

    def to_thrift(self) -> ttypes.RenderResult:
        return ttypes.RenderResult(
            self.table.to_thrift(),
            [e.to_thrift() for e in self.errors],
            "" if self.json is None else json_encode(self.json),
        )

    @property
    def status(self) -> str:
        """
        Return "ok", "error" or "unreachable".

        "ok" means there is a table as output.

        "error" means there are no table columns and error messages have been
        set by the module.

        "unreachable" means there are no table columns. (We stop rendering when
        a tab has no more columns -- hence the name, "unreachable".) Modules may
        return a result in this state, but it's usually not what the user wants.
        Modules should return error messages to help the user arrive at "ok".
        """
        if not self.table.metadata.columns:
            if self.errors:
                return "error"
            else:
                return "unreachable"
        else:
            return "ok"