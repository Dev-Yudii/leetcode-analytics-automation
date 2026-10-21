import html
import re
from datetime import datetime
from pathlib import Path

from scripts.db_utils import get_output_path
from scripts.topics import folder_name_for_topic
from scripts.translator import parse_input, parse_output

# Folder used when the source has no topic at all
GENERAL_FOLDER = "general"

# Characters that are not allowed in file names on Windows
ILLEGAL_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')

EXAMPLE_HEADER = re.compile(r"^Example\s+\d+\s*:", re.IGNORECASE)
CONSTRAINTS_HEADER = re.compile(r"^Constraints\s*:", re.IGNORECASE)
INPUT_LINE = re.compile(r"^Input\s*:\s*(.*)$", re.IGNORECASE)
OUTPUT_LINE = re.compile(r"^Output\s*:\s*(.*)$", re.IGNORECASE)


def clean_html(html_content):
    """Remove HTML tags and decode entities for the docstring."""
    if not html_content:
        return ""
    text = re.sub(r'</p>|<br\s*/?>|<li>|</div>', '\n', html_content)
    text = re.compile(r'<[^>]+>').sub('', text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join([line for line in lines if line])


def extract_inputs(html_content):
    """Scrape the HTML content to find the example inputs and outputs.

    Only the example blocks are read, so an "Input:" mentioned in the
    description does not become a fake test case.
    """
    cleaned = clean_html(html_content)
    lines = [line for line in cleaned.split('\n') if line.strip()]

    pairs = []
    seen_example = False
    current_input = None

    for index, line in enumerate(lines):
        if EXAMPLE_HEADER.match(line):
            seen_example = True
            current_input = None
            continue
        if CONSTRAINTS_HEADER.match(line):
            break
        if not seen_example:
            continue

        input_match = INPUT_LINE.match(line)
        if input_match:
            value = input_match.group(1).strip()
            if not value and index + 1 < len(lines):
                # "Input:" alone on a line, the value comes on the next one
                value = lines[index + 1].strip()
            current_input = value
            continue

        output_match = OUTPUT_LINE.match(line)
        if output_match and current_input is not None:
            pairs.append((current_input, output_match.group(1).strip()))
            current_input = None

    if pairs:
        return pairs

    # Fallback for content without the usual "Example N:" blocks
    inputs = re.findall(r'Input:\s*(.*)', cleaned, re.IGNORECASE)
    outputs = re.findall(r'Output:\s*(.*)', cleaned, re.IGNORECASE)
    fallback = []
    for position, raw_input in enumerate(inputs):
        raw_output = outputs[position].strip() if position < len(outputs) else ""
        fallback.append((raw_input.strip(), raw_output))
    return fallback


def parse_function_call(code_snippet):
    """Extract method name from the code snippet to build the print statement."""
    # Regex to find 'def method_name(self, ...)'
    match = re.search(r'def\s+(\w+)\s*\(', code_snippet)
    if match:
        return match.group(1)
    return "method_name"


def relative_file_path(challenge_data) -> str:
    """Relative path of the solution file, as stored in the database.

    The first topic decides the folder. It is a filesystem organization
    rule only, not a classification of the problem.
    """
    topics = challenge_data.get("topics") or []
    folder = folder_name_for_topic(topics[0]) if topics else GENERAL_FOLDER
    problem_id = challenge_data.get("id")
    slug = challenge_data.get("slug") or f"problem-{problem_id}"
    filename = ILLEGAL_PATH_CHARS.sub("_", f"{problem_id}_{slug}.py")
    return f"{folder}/{filename}"


def determine_file_path(challenge_data) -> Path:
    """Absolute path of the solution file, inside the output folder."""
    return get_output_path() / relative_file_path(challenge_data)


def _build_test_lines(challenge_data, method_name):
    """Build the local test block of the generated file."""
    raw_examples = extract_inputs(challenge_data.get("content"))
    test_lines = []

    for index, (raw_input, raw_output) in enumerate(raw_examples, 1):
        parsed = parse_input(raw_input)
        expected, expected_ok = parse_output(raw_output)
        expected_literal = repr(expected) if expected_ok else repr(raw_output)

        test_lines.append(f"    # Example Input: {raw_input}  |  Expected Output: {raw_output}")

        if not parsed.ok:
            # The input is not a literal: keep the example visible without
            # writing code that would break the file.
            test_lines.append("    # (not auto-translated — write this test manually)")
            test_lines.append("")
            continue

        if parsed.positional:
            test_lines.append(f"    inputs{index} = {parsed.literal}")
            call = f"solution.{method_name}(inputs{index})"
        else:
            test_lines.append(f"    inputs{index} = {parsed.literal}")
            call = f"solution.{method_name}(**inputs{index})"

        test_lines.append(
            f"    print(f'Test {index} Result:', {call}, ' | Expected:', {expected_literal})"
        )
        test_lines.append("")

    if not test_lines:
        test_lines.append("    # No explicit examples found. Add your manual tests below:")
        test_lines.append(f"    # print(solution.{method_name}())")

    return test_lines


def _build_code_block(code_snippet, method_name):
    """Starter code of the generated file, always ending in a valid body."""
    code_block = code_snippet or ""
    if code_block:
        if code_block.strip().endswith(":"):
            code_block = code_block.rstrip() + "\n        pass"
    else:
        # No starter code came from the source: the signature stays generic
        # so the local test block still runs.
        code_block = (
            "class Solution:\n"
            f"    def {method_name}(self, *args, **kwargs):\n"
            "        pass"
        )
    return code_block


def generate_daily_file(challenge_data, file_path=None) -> str:
    """Create the solution file for the challenge.

    The file is never overwritten: an existing file holds the personal
    solution and is left untouched. The database is not touched here
    (docs/architecture.md, section 17).
    """
    filepath = Path(file_path) if file_path else determine_file_path(challenge_data)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        print(f"File {filepath.name} already exists. Skipping generation.")
        return str(filepath)

    method_name = parse_function_call(challenge_data.get("code_snippet") or "")
    topics_str = ", ".join(challenge_data.get("topics") or [])
    code_block = _build_code_block(challenge_data.get("code_snippet"), method_name)
    test_lines = _build_test_lines(challenge_data, method_name)

    # Build the blueprint layout for daily practice
    now = datetime.now().astimezone()
    offset_h = int(now.utcoffset().total_seconds() // 3600)
    extracted_on = f"{now:%Y-%m-%d %H:%M} (UTC{offset_h:+d})"
    file_template = f'''"""
This problem was extracted on {extracted_on} from LeetCode at {challenge_data.get('link')}.
You can check the full problem description there.
Problem Title:
    {challenge_data.get('title')}
Difficulty:
    {challenge_data.get('difficulty')}
Tags:
    {topics_str}
"""

{code_block}

if __name__ == "__main__":
    solution = Solution()
    print("Script generated! Configure your tests below:")
    print("-" * 40)
{"\n".join(test_lines)}
"""
Notes:
    -
"""
'''

    with open(str(filepath), "w", encoding="utf-8") as f:
        f.write(file_template)

    print(f"File successfully created: {filepath}")

    return str(filepath)
