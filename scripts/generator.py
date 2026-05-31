import os
import re
from pathlib import Path
from scripts.db_utils import execute_query, OUTPUT_BASE_PATH


def clean_html(html_content):
    """Remove HTML tags and fix special characters for the docstring."""
    if not html_content:
        return ""
    text = re.sub(r'</p>|<br\s*/?>|<li>|</div>', '\n', html_content)
    text = re.compile(r'<[^>]+>').sub('', text)
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join([line for line in lines if line])

def extract_inputs(html_content):
    """Scrape the HTML content to find Example Inputs and Outputs using regex."""
    cleaned = clean_html(html_content)

    # Captures inputs and outputs
    inputs = re.findall(r'Input:\s*(.*)', cleaned, re.IGNORECASE)
    outputs = re.findall(r'Output:\s*(.*)', cleaned, re.IGNORECASE)
    
    # Connect both arrays.
    test_cases = []
    for i in range(len(inputs)):
        inp = inputs[i].strip()
        out = outputs[i].strip() if i < len(outputs) else ""
        test_cases.append((inp, out))

    return test_cases

def parse_function_call(code_snippet):
    """Extract method name from the code snippet to build the print statement."""
    # Regex to find 'def method_name(self, ...)'
    match = re.search(r'def\s+(\w+)\s*\(', code_snippet)
    if match:
        return match.group(1)
    return "method_name"

def translate_to_python_syntax(input_str: str) -> str:
    """
    Translates LeetCode/JS types to valid Python syntax.
    Safely turns commas into semicolons outside of brackets for exec().
    """
    if not input_str:
        return ""
    
    # Direct translation for booleans and nulls
    translated = input_str.replace("true", "True").replace("false", "False").replace("null", "None")
    
    # Parse string to replace parameter commas with semicolons without breaking lists []
    parts = []
    bracket_level = 0
    current_part = []
    
    for char in translated:
        if char == '[':
            bracket_level += 1
        elif char == ']':
            bracket_level -= 1
        
        # If comma is outside brackets, it's a parameter separator -> turn into semicolon
        if char == ',' and bracket_level == 0:
            parts.append("".join(current_part).strip())
            current_part = []
        else:
            current_part.append(char)
            
    parts.append("".join(current_part).strip())
    return " ; ".join(parts)

def save_to_sqlite(challenge_data, topic_folder):
    """Save the problem metadata into a local SQLite database file using db_utils."""
    
    # Guaranteeing the table exists using the correct professional table name
    create_table_query = """
        CREATE TABLE IF NOT EXISTS leetcode_problems (
            id TEXT PRIMARY KEY,
            title TEXT,
            slug TEXT,
            link TEXT,
            difficulty TEXT,
            date_generated TEXT,
            category TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    """
    execute_query(create_table_query)
    
    # Insert new problem smoothly using safe parameterized query
    insert_query = """
        INSERT INTO leetcode_problems (id, title, slug, link, difficulty, date_generated, category)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    
    try:
        execute_query(insert_query, (
            challenge_data['id'],
            challenge_data['title'],
            challenge_data['slug'],
            challenge_data['link'],
            challenge_data['difficulty'],
            challenge_data['date'],
            topic_folder.upper()
        ))
        print("Local database updated via db_utils!")
    except Exception:
        # If the ID already exists, execute_query throws an error because of PRIMARY KEY
        print("Problem already registered in database. Skipping row insertion.")

def generate_daily_file(challenge_data):
    """Generate the category folder, code file with auto-tests, and update the database."""
    
    # Define folder name based on first topic or default to general
    if challenge_data['topics']:
        topic_folder = challenge_data['topics'][0].lower().replace(" ", "_")
    else:
        topic_folder = "general"
        
    # Build target directory path dynamically
    target_dir = OUTPUT_BASE_PATH/topic_folder
    filename = f"{challenge_data['id']}_{challenge_data['slug']}.py"
    filepath = target_dir/filename

    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Prevent overwriting daily code if script runs twice
    if filepath.exists():
        print(f"File {filename} already exists. Skipping generation.")
        return str(filepath)

    cleaned_content = clean_html(challenge_data['content'])
    topics_str = ", ".join(challenge_data['topics'])

    # Extract test inputs and method name for automation
    raw_inputs = extract_inputs(challenge_data['content'])
    method_name = parse_function_call(challenge_data['code_snippet'])
    
    # Dynamically build the main test lines block
    test_lines = []
    for i, (test_input, expected_output) in enumerate(raw_inputs, 1):
        # Translate types and structural syntax for Python compatibility
        python_ready_input = translate_to_python_syntax(test_input)
        python_ready_output = expected_output.replace("true", "True").replace("false", "False").replace("null", "None")
        
        test_lines.append(f"    # Example Input: {test_input}  |  Expected Output: {expected_output}")
        
        # If input has assignments, use safe execution environment + dictionary unpacking
        if "=" in python_ready_input:
            test_lines.append(f"    inputs{i} = {{}}")
            test_lines.append(f"    exec(\"{python_ready_input}\", {{}}, inputs{i})")
            test_lines.append(f"    print(f'Test {i} Result:', solution.{method_name}(**inputs{i}), ' | Expected:', '{python_ready_output}')")
        else:
            # Simple fallback for straight scalar parameters
            test_lines.append(f"    print(f'Test {i} Result:', solution.{method_name}({python_ready_input}), ' | Expected:', '{python_ready_output}')")
            
        test_lines.append("")

    if not test_lines:
        test_lines.append("    # No explicit examples found. Add your manual tests below:")
        test_lines.append(f"    # print(solution.{method_name}())")

    # Body will always have a "pass" so it doesn't return indentation error
    code_block = challenge_data['code_snippet']
    if code_block:
        if code_block.strip().endswith(":"):
            code_block = code_block.rstrip() + "\n        pass"
    else:
        code_block = """class Solution:\n    def method_name(self):\n        pass"""

    # Build the blueprint layout for daily practice 
    file_template = f'''"""
Problem:
    {challenge_data['title']}
Link:
    {challenge_data['link']}
Difficulty:
    {challenge_data['difficulty']}
Topics:
    {topics_str}
"""

{code_block}

if __name__ == "__main__":
    solution = Solution()
    print("Script generated! Configure your tests below:")
    print("-" * 40)
{"\n".join(test_lines)}
"""
Approach 1:
    - 
Issue:
    - 
Final Approach:
    - Approach - passed on LeetCode with
        Runtime - ms Beats -%
        Memory - MB Beats -%
Complexity:
    - Time: O()
    - Space: O()
Notes:
    - 
"""
'''

    # Write the code template file
    with open(str(filepath), "w", encoding="utf-8") as f:
        f.write(file_template)
        
    # Append this problem to our database
    save_to_sqlite(challenge_data, topic_folder)    

    print(f"Category folder guaranteed: {target_dir}")
    print(f"File successfully created: {filepath}")

    return str(filepath)