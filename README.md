# Personal LeetCode Automation & Data Pipeline

## Description
Personal data pipeline that fetches the LeetCode Daily Challenge via GraphQL (one request per day, no login), validates the response into metadata + collection warnings, tracks topic identity in a versioned catalog, generates a ready-to-solve Python file with auto-parsed test cases, and logs metadata into a local database (SQLite today, PostgreSQL planned).

The generated file is a local practice workspace: it opens in any Python 3 environment (e.g. VS Code) for solving and local test runs; the full submission, with all test cases, happens on LeetCode. Solved files live in the separate [LeetCode Solutions](https://github.com/Dev-Yudii/leetcode) repository; this repo holds only the automation.


## Disclaimer
Personal, educational data-pipeline project. Not affiliated with, endorsed, or sponsored by LeetCode.
- One request per day to the public Daily Challenge; no login, no credentials, no Premium content, no automated submissions.
- The tool downloads the daily tests and opens the file in any Python 3 environment (e.g. VS Code) for local practice; the full submission, with all test cases, must be done on LeetCode.
- Generated files keep metadata + link back to the original problem so readers solve it on LeetCode; full statements are not republished or stored.
- Purpose: daily-practice consistency, problem-solving training, learning ETL by doing, and building my own database of solving history.
- Use at your own risk. If you are LeetCode and object to this project, please contact me at dev.yudii@gmail.com — it will be discontinued as soon as the message is seen.


## About This Project
This project started with a simple daily frustration: I wanted to keep my LeetCode Daily Challenge solutions organized, and track my progress on GitHub without wasting time manually copying templates and code snippets. 

As someone studying **Data Analytics and Data Engineering**, I realized that instead of just creating a repository of static files, I could build a local automation tool that doubles as a personal data pipeline. Over time, this system will log some of my coding behavior, allowing me to feed a Business Intelligence (BI) dashboard to extract insights about my learning curve and performance.


## The API Challenge
During my initial research, I discovered that LeetCode does not provide a conventional REST API. Instead, it relies on a **GraphQL endpoint**. While less straightforward than traditional endpoints, it allowed me to design custom queries to fetch exactly what I need each day: the problem ID, title, difficulty, topic tags, markdown/HTML description, and the official Python3 starter code snippet.


## Current Tech Stack (Phase 1)
The project is currently built as a lightweight local Automation Script (MVP):
* **Python 3**: The core programming language for the automation logic.
* **Requests**: To communicate with LeetCode's GraphQL API.
* **SQLite3 (Built-in)**: A lightweight, serverless relational database used to store problem metadata and track my daily problem-solving status incrementally.
* **Pathlib & RE (Python Standard Libraries)**: For dynamic file/folder creation based on problem topics, and regular expressions to extract clean test cases from HTML descriptions.


## How It Works
1. **Fetch**: The script connects to LeetCode and pulls the active daily challenge data (one request per day, no login).
2. **Validate**: The response is checked field by field. Missing `questionFrontendId` blocks the run (no valid identity); any other missing/null/empty field becomes a collection warning and the run continues.
3. **Topics**: Topic names are normalized and registered incrementally into the versioned `data/topics.json` catalog (stable IDs, never reused).
4. **Generate**: It creates a ready-to-solve Python file named after the primary key (`{ID}_{slug}.py`) under the first topic's folder, with metadata header, starter code and auto-parsed local test cases.
5. **Log**: It registers the problem into a local `leetcode_history.db` file, initializing its status as `PENDING`.

> Design decisions (identity, topic catalog, pipeline order) live in [docs/architecture.md](./docs/architecture.md); the working plan lives in [TODO.md](./TODO.md).


## Roadmap
- [x] Daily fetch + local file generation + metadata logging
- [x] Topic catalog with stable IDs + collection warnings
- [ ] PostgreSQL (`problems`, `topics`, `problem_topics`) once the Python pipeline is stable
- [ ] Collection audit, backups, orchestration (Airflow) — later

See [TODO.md](./TODO.md) for the current working plan and [CHANGELOG.md](./CHANGELOG.md) for history.