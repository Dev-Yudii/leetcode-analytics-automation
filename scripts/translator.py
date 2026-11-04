"""Translation of LeetCode example text into real Python literals.

LeetCode describes examples with a JSON-ish notation: `true`, `false` and
`null` instead of Python's `True`, `False` and `None`. The previous approach
was a blind string replacement, which corrupted values inside strings
("nullable" became "Noneable") and split strings that contain commas
(`s = "a,b"` became `s = "a ; b"`, a SyntaxError).

This module scans the text instead of replacing it:
    * string literals are copied verbatim;
    * only standalone tokens outside strings are converted;
    * the result is validated with `ast.literal_eval` before it is trusted.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Any

LEETCODE_LITERALS = {
    "true": "True",
    "false": "False",
    "null": "None",
}

IDENTIFIER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
QUOTE_CHARS = ("'", '"')
WHITESPACE = " \t"

# LeetCode writes big numbers with thousand separators: 1,000,000
THOUSAND_SEPARATED_NUMBER = re.compile(r"^\d{1,3}(,\d{3})+$")


@dataclass
class ParsedInput:
    """Result of parsing one example input.

    parameters: {name: value} when the example uses named arguments
    value:      the single positional value when the example has no names
    literal:    Python source of the value(s), ready to be written to a file
    ok:         False when the text could not be parsed as a literal
    """

    raw: str
    literal: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    value: Any = None
    positional: bool = False
    ok: bool = False

    def render(self) -> str:
        """Python source to assign this input in the generated file."""
        return self.literal


def _end_of_string(text: str, start: int) -> int:
    """Index just after the string literal that starts at `start`."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return len(text)


def _top_level_positions(text: str, wanted: str) -> list[int]:
    """Indices of `wanted` chars that are outside strings and outside brackets."""
    positions = []
    depth = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in QUOTE_CHARS:
            index = _end_of_string(text, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0 and char in wanted:
            positions.append(index)
        index += 1
    return positions


def find_assignments(text: str) -> list[tuple[str, str]]:
    """Split example text into (name, raw_value) pairs.

    'nums1 = [1,2], nums2 = [3]' -> [('nums1', '[1,2]'), ('nums2', '[3]')]

    Returns an empty list when the text is not a list of named assignments
    (a single positional value, for example).
    """
    equals = _top_level_positions(text, "=")
    if not equals:
        return []

    assignments = []
    for position, equal in enumerate(equals):
        name_end = equal
        while name_end > 0 and text[name_end - 1] in WHITESPACE:
            name_end -= 1
        name_start = name_end
        while name_start > 0 and text[name_start - 1] in IDENTIFIER_CHARS:
            name_start -= 1
        name = text[name_start:name_end]
        if not name or not (name[0].isalpha() or name[0] == "_"):
            return []

        value_start = equal + 1
        if position + 1 < len(equals):
            next_equal = equals[position + 1]
            name_end = next_equal
            while name_end > value_start and text[name_end - 1] in WHITESPACE:
                name_end -= 1
            name_start = name_end
            while name_start > value_start and text[name_start - 1] in IDENTIFIER_CHARS:
                name_start -= 1
            value_end = name_start
        else:
            value_end = len(text)

        value = text[value_start:value_end].strip()
        if value.endswith(","):
            value = value[:-1].rstrip()
        assignments.append((name, value))

    return assignments


def convert_leetcode_literals(text: str) -> str:
    """Convert standalone true/false/null tokens into Python literals.

    Tokens inside string literals are preserved, so "nullable" and
    "true story" survive untouched.
    """
    result = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in QUOTE_CHARS:
            end = _end_of_string(text, index)
            result.append(text[index:end])
            index = end
            continue
        if char.isalpha() or char == "_":
            end = index
            while end < length and (text[end].isalnum() or text[end] == "_"):
                end += 1
            word = text[index:end]
            result.append(LEETCODE_LITERALS.get(word, word))
            index = end
            continue
        result.append(char)
        index += 1
    return "".join(result)


def parse_literal(text: str) -> tuple[Any, bool]:
    """Parse a LeetCode literal into a Python value.

    Returns (value, True) on success and (None, False) when the text is not
    a literal. Never raises: an unparseable value is a normal observation,
    not an error.
    """
    converted = convert_leetcode_literals(text.strip())
    if not converted:
        return None, False

    # 1,000 is a number with thousand separators, not a tuple.
    if THOUSAND_SEPARATED_NUMBER.match(converted):
        converted = converted.replace(",", "")

    # A bare "1,2" is not valid Python: tuples must be written with parens.
    if "," in converted and not converted.startswith("("):
        if _top_level_positions(converted, ","):
            return None, False

    try:
        return ast.literal_eval(converted), True
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None, False


def parse_input(text: str) -> ParsedInput:
    """Parse an example input into named parameters or a positional value."""
    raw = (text or "").strip()
    parsed = ParsedInput(raw=raw)
    if not raw:
        return parsed

    assignments = find_assignments(raw)
    if assignments:
        parameters = {}
        for name, raw_value in assignments:
            value, ok = parse_literal(raw_value)
            if not ok:
                parsed.ok = False
                return parsed
            parameters[name] = value
        parsed.parameters = parameters
        parsed.literal = repr(parameters)
        parsed.ok = True
        return parsed

    value, ok = parse_literal(raw)
    if ok:
        parsed.value = value
        parsed.positional = True
        parsed.literal = repr(value)
        parsed.ok = True
    return parsed


def parse_output(text: str) -> tuple[Any, bool]:
    """Parse an example output into a Python value (same rules as the input)."""
    return parse_literal(text)
