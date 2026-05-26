from scripts.leetcode_client import get_daily_challenge
from scripts.generator import generate_daily_file

def main():
    print("Connecting to LeetCode API...")
    try:
        # Fetching today's data from the graphql client
        challenge_data = get_daily_challenge()
        
        print("Generating local environment...")
        # Processing and creating the files dynamically using generator.py
        generate_daily_file(challenge_data)
        
    except Exception as e:
        # Treatment for any unexpected fail during the pipeline
        print(f"Process failed: {e}")

if __name__ == "__main__":
    main()