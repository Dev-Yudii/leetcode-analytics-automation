import requests

# Leetcode "API" URL
LEETCODE_URL = "https://leetcode.com/graphql/"

def get_daily_challenge():
    # Asssigning request into variable for daily challenge infos: {date, url}
    query = """
    query questionOfToday {
        activeDailyCodingChallengeQuestion {
            date
            link
            question {
                questionId
                title
                titleSlug
                difficulty
                content
                topicTags {
                    name
                }
                codeSnippets {
                    lang
                    code
                }
            }
        }
    }
    """

    # Simulating browser access
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    # Getting the response after requesting through POST
    response = requests.post(LEETCODE_URL, json={"query": query}, headers=headers)

    # Treatment for connection fail
    if response.status_code != 200:
        raise Exception(f"Error connecting to Leetcode.com: {response.status_code}")
    

    # Organizing the data so we can use it later
    raw_data = response.json()['data']['activeDailyCodingChallengeQuestion']
    question_info = raw_data['question']

    # We will always use python, so we just need Python3.
    python_snippet = ""
    for snippet in question_info['codeSnippets']:
        if snippet['lang'] == "Python3":
            python_snippet = snippet['code']
            break
    
    # We will extract topics in a string list, later those will be used for organizing the files
    topics = [tag['name'] for tag in question_info['topicTags']]

    # This will be the base for the structure in the python file our script will generate
    formatted_data = {
        "id": question_info['questionId'],
        "date": raw_data['date'],
        "title": question_info['title'],
        "slug": question_info['titleSlug'],
        "link": f"https://leetcode.com{raw_data['link']}",
        "difficulty": question_info['difficulty'],
        "content": question_info['content'],
        "topics": topics,
        "code_snippet": python_snippet
    }

    return formatted_data

