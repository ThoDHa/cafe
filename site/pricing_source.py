"""Priced drink rows from the cost workbook, for the site generator.

This module is the seam between recipes/cafe_costs.xlsx and the public
menus site: it turns the workbook's Drinks sheet into DrinkCost rows and
holds the small curation the join onto cafe.md needs (name aliases, the
Bạc Xỉu insertion item and its anchor). The workbook is written by script
and never recalculated, so every computed cell arrives as an uncached
formula string: this module evaluates the chain itself, from the
Ingredients cost-per-gram column through the Bases batch costs to each
drink's Total Cost and Menu Price. The Total Cost and Menu Price
relationships are the workbook owner's to change; this module evaluates
whatever the Drinks D and F columns say at call time and hardcodes no
pricing model.

Formulas are evaluated through a strict tokenizer and recursive-descent
parser supporting exactly the grammar the workbook uses: decimal and
integer literals, + - * /, parentheses, optionally sheet-qualified,
optionally $-anchored A1 cell references, and three Excel functions with
comma-separated arguments (MAX, ROUND, and ROUNDUP, with Excel's
away-from-zero rounding). Function-name lookup is case-sensitive, unlike
Excel: a lowercase round( from an owner edit fails as an unknown
function, so owners write function names uppercase as the workbook does.
Anything else (other function calls, ranges,
cross-row arithmetic Excel would accept but this workbook does not use)
fails loudly naming the sheet, cell, and formula, and file-sourced
strings are never passed to eval. Cells resolve lazily with memoization so
formulas referencing formulas resolve once, and reference cycles fail
loudly.

openpyxl imports lazily so the module itself stays stdlib-only; run the
generator under `uv run --with openpyxl` like the site's other
dependency-gated invocations.
"""

from __future__ import annotations

import enum
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_UP
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
MENU_DIR = REPO_ROOT / "menu"
DEFAULT_COSTS: Path = REPO_ROOT.parent / "recipes" / "cafe_costs.xlsx"

sys.path.insert(0, str(MENU_DIR))

from menu_source import Item  # noqa: E402

PRICE_ALIASES: dict[str, str] = {
    "Pour Over": "Pour Over Coffee",
    "Vietnamese Coffee": "Vietnamese Iced Coffee",
}
BAC_XIU_ANCHOR: str = "House Latte"
BAC_XIU: Item = Item(
    name_en="Bạc Xỉu",
    name_vi="Cà Phê Bạc Xỉu",
    description=(
        "The classic milkier white coffee: the House Latte built on "
        "condensed milk instead of syrup."
    ),
    temperatures=["hot", "iced"],
)

DRINKS_SHEET = "Drinks"
FIRST_DATA_ROW = 2
DRINK_NAME_COLUMN = "A"
DRINK_TOTAL_COST_COLUMN = "D"
DRINK_MENU_PRICE_COLUMN = "F"


@dataclass
class DrinkCost:
    """One priced drink row from the workbook's Drinks sheet.

    ``name`` is the Drinks-sheet row name verbatim, ``cost`` the evaluated
    Total Cost, and ``suggested`` the evaluated Menu Price. Values are
    unrounded floats; the pages format them for display.
    """

    name: str
    cost: float
    suggested: float


class FormulaError(Exception):
    """Raised when a workbook formula cannot be evaluated.

    The message names the sheet, cell coordinate, and formula text (plus
    the chain of referencing cells when the failure sits in a referenced
    cell), so a broken workbook edit fails the build at the exact cell.
    """


class _FormulaSyntaxError(Exception):
    """Internal: a formula body outside the supported grammar."""


class _TokenKind(enum.Enum):
    NUMBER = enum.auto()
    CELL = enum.auto()
    FUNC = enum.auto()
    OPERATOR = enum.auto()
    LPAREN = enum.auto()
    RPAREN = enum.auto()
    COMMA = enum.auto()


@dataclass(frozen=True)
class _CellReference:
    """A parsed cell reference; ``sheet`` is None for same-sheet refs."""

    sheet: str | None
    coordinate: str


@dataclass(frozen=True)
class _Token:
    """One formula token: a number, a cell reference, a function name, or
    a punctuation mark.

    ``number`` carries NUMBER's value and ``reference`` CELL's parsed
    target; FUNC, OPERATOR, LPAREN, RPAREN, and COMMA carry only their
    ``text``.
    """

    kind: _TokenKind
    text: str
    number: float = 0.0
    reference: _CellReference | None = None


# The workbook grammar, one alternative per token kind. A function name
# only tokenizes when a call parenthesis follows it, so a bare word like a
# misspelled function surfaces as unsupported syntax; a range colon
# likewise never tokenizes.
_FORMULA_TOKEN_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)"
    r"|(?P<cell>(?:(?:'[^']+'|[A-Za-z_][A-Za-z0-9_]*)!)?\$?[A-Za-z]{1,3}\$?\d+)"
    r"|(?P<func>[A-Za-z_][A-Za-z0-9_]*(?=\s*\())"
    r"|(?P<operator>[+\-*/])"
    r"|(?P<lparen>\()"
    r"|(?P<rparen>\))"
    r"|(?P<comma>,)"
)

# Splits a cell token into its optional sheet name (quoted or bare), its
# column letters, and its row digits, dropping the $ anchors.
_CELL_REFERENCE_RE = re.compile(
    r"(?:(?:'(?P<quoted_sheet>[^']+)'|(?P<bare_sheet>[A-Za-z_][A-Za-z0-9_]*))!)?"
    r"\$?(?P<column>[A-Za-z]{1,3})\$?(?P<row>\d+)"
)

_WHITESPACE_RE = re.compile(r"\s+")

# Bounds the unsupported-syntax snippet so one typo cannot flood the build
# log with the rest of the formula.
_UNSUPPORTED_SYNTAX_SNIPPET = 20


def _tokenize(formula_body: str) -> list[_Token]:
    """Split a formula body (the text after '=') into tokens.

    Raises ``_FormulaSyntaxError`` naming the first substring that the
    grammar cannot express.
    """

    tokens: list[_Token] = []
    position = 0
    while position < len(formula_body):
        whitespace = _WHITESPACE_RE.match(formula_body, position)
        if whitespace is not None:
            position = whitespace.end()
            continue
        match = _FORMULA_TOKEN_RE.match(formula_body, position)
        if match is None:
            snippet = formula_body[position : position + _UNSUPPORTED_SYNTAX_SNIPPET]
            raise _FormulaSyntaxError(f"unsupported syntax near {snippet!r}")
        tokens.append(_token_from_match(match))
        position = match.end()
    return tokens


def _token_from_match(match: re.Match[str]) -> _Token:
    """Build the token for one tokenizer match."""

    kind_group = match.lastgroup
    text = match.group()
    if kind_group == "number":
        return _Token(_TokenKind.NUMBER, text, number=float(text))
    if kind_group == "cell":
        parts = _CELL_REFERENCE_RE.fullmatch(text)
        assert parts is not None, f"token {text!r} matched but does not reparse"
        sheet = parts.group("quoted_sheet") or parts.group("bare_sheet")
        coordinate = f"{parts.group('column').upper()}{parts.group('row')}"
        return _Token(
            _TokenKind.CELL, text, reference=_CellReference(sheet, coordinate)
        )
    if kind_group == "operator":
        return _Token(_TokenKind.OPERATOR, text)
    if kind_group == "func":
        return _Token(_TokenKind.FUNC, text)
    if kind_group == "comma":
        return _Token(_TokenKind.COMMA, text)
    if kind_group == "lparen":
        return _Token(_TokenKind.LPAREN, text)
    assert kind_group == "rparen", f"unhandled token group {kind_group!r}"
    return _Token(_TokenKind.RPAREN, text)


def _excel_rounded(arguments: list[float], rounding: str, name: str) -> float:
    """Round argument 0 to argument 1 places in the given Decimal mode.

    ``rounding`` is a Decimal rounding mode: ROUND passes ROUND_HALF_UP
    (ties away from zero) and ROUNDUP passes ROUND_UP (any remainder away
    from zero); Python's round() is half-even and would silently flip a
    workbook tie. A magnitude beyond the evaluator's decimal precision
    raises ``FormulaError`` like any other unevaluable formula.
    """

    if len(arguments) != 2:
        raise _FormulaSyntaxError(
            f"{name} needs exactly 2 arguments, got {len(arguments)}"
        )
    try:
        quantum = Decimal(1).scaleb(-int(arguments[1]))
        rounded = Decimal(str(arguments[0])).quantize(quantum, rounding=rounding)
    except (InvalidOperation, OverflowError, ValueError):
        raise FormulaError(
            f"{name}({arguments[0]!r}, {arguments[1]!r}) overflows the "
            "evaluator's decimal precision"
        ) from None
    return float(rounded)


def _excel_max(arguments: list[float]) -> float:
    """Return the largest of two or more arguments, Excel MAX."""

    if len(arguments) < 2:
        raise _FormulaSyntaxError(
            f"MAX needs at least 2 arguments, got {len(arguments)}"
        )
    return max(arguments)


def _excel_round(arguments: list[float]) -> float:
    """Round argument 0 to argument 1 places, ties away from zero, Excel
    ROUND."""

    return _excel_rounded(arguments, ROUND_HALF_UP, "ROUND")


def _excel_roundup(arguments: list[float]) -> float:
    """Round any remainder away from zero to argument 1 places, Excel
    ROUNDUP."""

    return _excel_rounded(arguments, ROUND_UP, "ROUNDUP")


# The workbook's function vocabulary, one entry per supported name: the
# charm-pricing formula calls MAX, ROUND, and ROUNDUP, and any other name
# fails loudly at parse time.
_EXCEL_FUNCTIONS = {
    "MAX": _excel_max,
    "ROUND": _excel_round,
    "ROUNDUP": _excel_roundup,
}


class _FormulaParser:
    """Recursive-descent evaluator for one formula body.

    Grammar: expression := term (('+'|'-') term)*; term := factor
    (('*'|'/') factor)*; factor := NUMBER | CELL | '(' expression ')' |
    FUNC '(' expression (',' expression)* ')'. Cell references resolve
    through the workbook's memoized evaluator as the parse reaches them,
    so nested formulas resolve lazily.
    """

    def __init__(self, tokens: list[_Token], sheet: str, values: _WorkbookValues):
        self._tokens = tokens
        self._sheet = sheet
        self._values = values
        self._position = 0

    def parse(self) -> float:
        """Evaluate the full token list to one number.

        Raises ``_FormulaSyntaxError`` for grammar violations and
        ``FormulaError`` for unresolvable references or division by zero.
        """

        value = self._parse_expression()
        if self._position != len(self._tokens):
            trailing = self._tokens[self._position]
            raise _FormulaSyntaxError(f"unexpected {trailing.text!r} after expression")
        return value

    def _parse_expression(self) -> float:
        value = self._parse_term()
        while self._peek_operator() in ("+", "-"):
            operator = self._advance().text
            right = self._parse_term()
            value = value + right if operator == "+" else value - right
        return value

    def _parse_term(self) -> float:
        value = self._parse_factor()
        while self._peek_operator() in ("*", "/"):
            operator = self._advance().text
            right = self._parse_factor()
            if operator == "*":
                value = value * right
            elif right == 0:
                raise FormulaError("division by zero")
            else:
                value = value / right
        return value

    def _parse_factor(self) -> float:
        token = self._current()
        if token.kind is _TokenKind.NUMBER:
            self._advance()
            return token.number
        if token.kind is _TokenKind.CELL:
            self._advance()
            assert token.reference is not None
            sheet = (
                token.reference.sheet
                if token.reference.sheet is not None
                else self._sheet
            )
            return self._values.value(sheet, token.reference.coordinate)
        if token.kind is _TokenKind.FUNC:
            self._advance()
            return self._parse_function_call(token.text)
        if token.kind is _TokenKind.LPAREN:
            self._advance()
            value = self._parse_expression()
            closing = self._current()
            if closing.kind is not _TokenKind.RPAREN:
                raise _FormulaSyntaxError(
                    f"expected ')' after expression, found {closing.text!r}"
                )
            self._advance()
            return value
        raise _FormulaSyntaxError(f"unexpected {token.text!r}")

    def _parse_function_call(self, name: str) -> float:
        """Evaluate one call: ``name`` '(' expression (',' expression)* ')'."""

        function = _EXCEL_FUNCTIONS.get(name)
        if function is None:
            raise _FormulaSyntaxError(f"unknown function {name!r}")
        self._advance()
        arguments = [self._parse_expression()]
        while self._current().kind is _TokenKind.COMMA:
            self._advance()
            arguments.append(self._parse_expression())
        closing = self._current()
        if closing.kind is not _TokenKind.RPAREN:
            raise _FormulaSyntaxError(
                f"expected ')' after the {name} arguments, found {closing.text!r}"
            )
        self._advance()
        return function(arguments)

    def _current(self) -> _Token:
        if self._position >= len(self._tokens):
            raise _FormulaSyntaxError("unexpected end of formula")
        return self._tokens[self._position]

    def _advance(self) -> _Token:
        token = self._current()
        self._position += 1
        return token

    def _peek_operator(self) -> str | None:
        if self._position >= len(self._tokens):
            return None
        token = self._tokens[self._position]
        if token.kind is not _TokenKind.OPERATOR:
            return None
        return token.text


class _WorkbookValues:
    """Memoized lazy evaluator for every cell of one loaded workbook.

    Sheets map to coordinate-keyed raw values (numbers or '='-prefixed
    formula strings, None/absent for empty). ``value`` resolves a cell on
    first request and memoizes it, tracks the resolution stack to detect
    reference cycles, and formats every failure with the failing cell's
    sheet, coordinate, and formula text plus the chain of referencing
    cells.
    """

    def __init__(self, cells: dict[str, dict[str, float | str]]):
        self._cells = cells
        self._values: dict[tuple[str, str], float] = {}
        self._resolving: set[tuple[str, str]] = set()

    @classmethod
    def from_openpyxl(cls, workbook: openpyxl.Workbook) -> _WorkbookValues:
        """Snapshot raw cell values from a loaded openpyxl workbook."""

        cells: dict[str, dict[str, float | str]] = {}
        for worksheet in workbook.worksheets:
            sheet_cells: dict[str, float | str] = {}
            for row in worksheet.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        sheet_cells[cell.coordinate] = cell.value
            cells[worksheet.title] = sheet_cells
        return cls(cells)

    def value(self, sheet: str, coordinate: str) -> float:
        """Return the numeric value of one cell, evaluating formulas lazily.

        Raises ``FormulaError`` for unknown sheets, empty or non-numeric
        cells, unevaluable formulas, and reference cycles.
        """

        key = (sheet, coordinate)
        if key in self._values:
            return self._values[key]
        if key in self._resolving:
            raise FormulaError(f"reference cycle resolving {sheet}!{coordinate}")
        self._resolving.add(key)
        try:
            result = self._evaluate_cell(sheet, coordinate)
        finally:
            self._resolving.discard(key)
        self._values[key] = result
        return result

    def _evaluate_cell(self, sheet: str, coordinate: str) -> float:
        if sheet not in self._cells:
            raise FormulaError(f"unknown sheet {sheet!r}")
        raw = self._cells[sheet].get(coordinate)
        if raw is None:
            raise FormulaError(
                f"empty cell {sheet}!{coordinate} where a number is needed"
            )
        if isinstance(raw, str):
            return self._evaluate_formula(sheet, coordinate, raw)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise FormulaError(
                f"{sheet}!{coordinate} holds {type(raw).__name__} where a "
                "number is needed"
            )
        return float(raw)

    def _evaluate_formula(self, sheet: str, coordinate: str, formula: str) -> float:
        if not formula.startswith("="):
            raise FormulaError(
                f"{sheet}!{coordinate} holds text {formula!r} where a number "
                "is needed"
            )
        try:
            parser = _FormulaParser(_tokenize(formula[1:]), sheet, self)
            return parser.parse()
        except _FormulaSyntaxError as exc:
            raise FormulaError(f"{sheet}!{coordinate} {formula!r}: {exc}") from None
        except FormulaError as exc:
            raise FormulaError(f"{exc} (via {sheet}!{coordinate})") from None


def _load_openpyxl() -> ModuleType:
    """Import openpyxl lazily, mirroring generate.py's weasyprint loader.

    Returns the openpyxl module. Raises ``RuntimeError`` naming the exact
    uv invocation when the dependency is absent, so the guidance survives
    into build logs where the import alone would print a bare module name.
    """

    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError(
            "reading the cost workbook requires openpyxl; run the generator "
            "via 'uv run --with openpyxl python site/generate.py'"
        ) from exc
    return openpyxl


def read_drink_costs(path: Path = DEFAULT_COSTS) -> list[DrinkCost]:
    """Read one priced row per Drinks-sheet data row, in sheet order.

    The Total Cost and Menu Price cells are evaluated through the
    workbook's own formula chain at call time, so any workbook edit (an
    ingredient price, a base recipe, the pricing relationships in the D
    and F columns) reprices the rows on the next call. Raises
    ``RuntimeError`` when openpyxl is absent, ``FormulaError`` when any
    formula is outside the grammar, unresolvable, or cyclic,
    ``ValueError`` for a non-text drink name, and ``FileNotFoundError``
    for a missing workbook.

    Parameters:
        path: the cost workbook; defaults to the sibling recipes checkout.
    """

    openpyxl = _load_openpyxl()
    workbook = openpyxl.load_workbook(path, data_only=False)
    values = _WorkbookValues.from_openpyxl(workbook)
    try:
        drinks = workbook[DRINKS_SHEET]
    except KeyError as exc:
        raise RuntimeError(
            f"{path} has no {DRINKS_SHEET!r} sheet; the priced pages are "
            "generated from it"
        ) from exc
    rows: list[DrinkCost] = []
    for row_number in range(FIRST_DATA_ROW, drinks.max_row + 1):
        name_cell = drinks[f"{DRINK_NAME_COLUMN}{row_number}"].value
        if name_cell is None:
            continue
        if not isinstance(name_cell, str):
            raise ValueError(
                f"{DRINKS_SHEET}!{DRINK_NAME_COLUMN}{row_number} holds "
                f"{type(name_cell).__name__}; expected a drink name"
            )
        cost = values.value(DRINKS_SHEET, f"{DRINK_TOTAL_COST_COLUMN}{row_number}")
        suggested = values.value(
            DRINKS_SHEET, f"{DRINK_MENU_PRICE_COLUMN}{row_number}"
        )
        rows.append(DrinkCost(name=name_cell, cost=cost, suggested=suggested))
    return rows
