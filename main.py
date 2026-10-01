from scripts.leetcode_client import get_daily_challenge
from scripts.generator import generate_daily_file
from scripts.topics import normalize_topic_name, get_or_create_topic_id

def main():
    print("Connecting to LeetCode API...")
    try:
        # Fetching today's data from the graphql client
        challenge_data = get_daily_challenge()
    except Exception as e:
        # Block 1 (fatal): fetch failed, nothing else can run
        print(f"Failed to fetch challenge: {e}")
        return

    # Collection warnings from the fetch step (non-fatal, run continues)
    for warning in challenge_data.get("warnings", []):
        print(warning)

    # Identity check (defensive): without an ID there is no valid problem
    if challenge_data.get("id") is None or (
        isinstance(challenge_data.get("id"), str) and not challenge_data["id"].strip()
    ):
        print(
            "Challenge without ID (questionFrontendId missing). Skipping save. "
            f"Seen: title={challenge_data.get('title')!r} date={challenge_data.get('date')!r}"
        )
        return

    # Block 2 (warnings only): register topics incrementally.
    # A catalog failure must not block file generation.
    try:
        raw_topics = challenge_data.get("topics")
        if not isinstance(raw_topics, list):
            print("Warning: field 'topics' in unexpected format — fell back to 'general' folder")
            raw_topics = []
        elif len(raw_topics) == 0:
            print("Warning: topics missing/empty — fell back to 'general' folder")

        topic_ids = {}
        for raw_name in raw_topics:
            if not isinstance(raw_name, str) or not raw_name.strip():
                print(f"Warning: invalid topic {raw_name!r} — skipped the item")
                continue
            normalized = normalize_topic_name(raw_name)
            try:
                topic_ids[normalized] = get_or_create_topic_id(raw_name)
            except Exception as e:
                print(f"Warning: failed to register topic '{normalized}': {e}. Continued anyway.")

        if topic_ids:
            summary = ", ".join(f"{name}->{tid}" for name, tid in topic_ids.items())
            print(f"Topics: {summary}")
    except Exception as e:
        print(f"Warning: failed to process topics: {e}. Continued to generation anyway.")

    print("Generating local environment...")
    try:
        # Processing and creating the files dynamically using generator.py
        # Persistence (SQLite) is unchanged in this step.
        generate_daily_file(challenge_data)
    except Exception as e:
        # Block 3 (fatal for this run): generation failed
        print(f"Failed to generate file: {e}")
        return

if __name__ == "__main__":
    main()