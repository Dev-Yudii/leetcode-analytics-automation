import os
import re
import sqlite3

# Adjust paths according to what you want.

# Discover where generator.py is located (project/scripts)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Go up two levels to reach the root workspace directory
DEVELOPER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))

# Path where problem-solving repository will live
OUTPUT_BASE_PATH = os.path.join(DEVELOPER_DIR, "Problem-Solving", "LeetCode")

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

def save_to_sqlite(challenge_data, topic_folder):
    """Save the problem metadata into a local SQLite database file for future BI connection."""
    db_path = os.path.join(OUTPUT_BASE_PATH, "leetcode_history.db")
    
    # Connects to the file (creates it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create the central log table if it's the first run
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS problems (
            id TEXT PRIMARY KEY,
            title TEXT,
            slug TEXT,
            link TEXT,
            difficulty TEXT,
            date_generated TEXT,
            category TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    """)
    
    # Insert new problem smoothly, skipping if the ID already exists
    try:
        cursor.execute("""
            INSERT INTO problems (id, title, slug, link, difficulty, date_generated, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            challenge_data['id'],
            challenge_data['title'],
            challenge_data['slug'],
            challenge_data['link'],
            challenge_data['difficulty'],
            challenge_data['date'],
            topic_folder.upper()
        ))
        conn.commit()
        print("📦 Local database leetcode_history.db updated!")
    except sqlite3.IntegrityError:
        # ID already exists in database, no actions needed
        print("ℹ️ Problem already registered in database. Skipping row insertion.")
    
    conn.close()

def generate_daily_file(challenge_data):
    """Generate the category folder, code file with auto-tests, and update the database."""
    
    # Define folder name based on first topic or default to general (Maybe in the future we can use subtopics, but let's see how it goes for now)
    if challenge_data['topics']:
        topic_folder = challenge_data['topics'][0].lower().replace(" ", "_")
    else:
        topic_folder = "general"
        
    # Build target directory path dynamically
    target_dir = os.path.join(OUTPUT_BASE_PATH, topic_folder)
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        
    filename = f"{challenge_data['id']}_{challenge_data['slug']}.py"
    filepath = os.path.join(target_dir, filename)
    
    # Prevent overwriting daily code if script runs twice (Cause we will try to automatize it later!)
    if os.path.exists(filepath):
        print(f"File {filename} already exists. Skipping generation.")
        return filepath

    cleaned_content = clean_html(challenge_data['content'])
    topics_str = ", ".join(challenge_data['topics'])

    # Extract test inputs and method name for automation
    raw_inputs = extract_inputs(challenge_data['content'])
    method_name = parse_function_call(challenge_data['code_snippet'])
    
    # Dynamically build the main test lines block
    test_lines = []
    for i, (test_input, expected_output) in enumerate(raw_inputs, 1):
        if expected_output:
            test_lines.append(f"    # Example Input: {test_input}  |  Expected Output: {expected_output}")
        else:
            test_lines.append(f"    # Example Input: {test_input}")
        
        if "=" in test_input:
            val = test_input.split("=", 1)[1].strip()
            test_lines.append(f"    testcase{i} = {val}")
        else:
            test_lines.append(f"    testcase{i} = {test_input}")
            
        test_lines.append(f"    print(f'Test {i} Result:', solution.{method_name}(testcase{i}))")
        test_lines.append("")

    if not test_lines:
        test_lines.append("    # No explicit examples found. Add your manual tests below:")
        test_lines.append(f"    # print(solution.{method_name}())")

    # Body will always have a "pass" so it doesn't return identation error;
    code_block = challenge_data['code_snippet']
    if code_block:
        if code_block.strip().endswith(":"):
            code_block = code_block.rstrip() + "\n        pass"
    else:
        code_block = """class Solution:\n    def method_name(self):\n        pass"""

    # Build the blueprint layout for daily practice 
    # The main goal for the project right now. The idea is not wasting time creating the same template daily for git upload
    file_template = f'''"""
Problem:
{challenge_data['title']}

Link:
{challenge_data['link']}

Difficulty:
{challenge_data['difficulty']}

Topics:
{topics_str}

Notes:
- 
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
- 

Complexity:
Time: O()
Space: O()

Notes:
- 
"""
'''

    # Write the code template file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(file_template)
        
    # Append this problem to our database
    save_to_sqlite(challenge_data, topic_folder)    

    print(f"Category folder guaranteed: {target_dir}")
    print(f"File successfully created: {filepath}")

    return filepath