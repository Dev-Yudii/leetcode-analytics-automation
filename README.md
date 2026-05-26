# Personal LeetCode Automation & Data Pipeline

## Description
Automated data pipeline that fetches the LeetCode Daily Challenge via GraphQL, dynamically generates a localized Python workspace with auto-parsed test cases, and logs metadata into a local SQLite database


## About This Project
This project started with a simple daily frustration: I wanted to solve the LeetCode Daily Challenge every day, keep my solutions organized, and track my progress on GitHub without wasting time manually copying templates and code snippets. 

As someone focused on **Data Analytics and Data Engineering**, I realized that instead of just creating a repository of static files, I could build a local automation tool that doubles as a personal data pipeline. Over time, this system will log my real coding behavior, allowing me to feed a Business Intelligence (BI) dashboard to extract insights about my learning curve and performance.


## The API Challenge
During my initial research, I discovered that LeetCode does not provide a conventional REST API. Instead, it relies on a **GraphQL endpoint**. While less straightforward than traditional endpoints, it allowed me to design custom queries to fetch exactly what I need each day: the problem ID, title, difficulty, topic tags, markdown/HTML description, and the official Python3 starter code snippet.


## Current Tech Stack (Phase 1)
The project is currently built as a lightweight local Automation Script (MVP):
* **Python 3**: The core programming language for the automation logic.
* **Requests**: To communicate with LeetCode's GraphQL API.
* **SQLite3 (Built-in)**: A lightweight, serverless relational database used to store problem metadata and track my daily problem-solving status incrementally.
* **OS & RE (Python Standard Libraries)**: For dynamic file/folder creation based on problem topics, and regular expressions to extract clean test cases from HTML descriptions.


## How It Works
1. **Fetch**: The script connects to LeetCode and pulls the active daily challenge data.
2. **Structure**: It checks the primary topic of the problem and dynamically guarantees a folder for that specific category (e.g., `hash_table/`, `array/`).
3. **Generate**: It creates a personalized Python template file named after the primary key (`{ID}_{slug}.py`) containing some of the problem data, a boilerplate class, and automatically parsed local test cases.
4. **Log**: It registers the problem into a local `leetcode_history.db` file, initializing its status as `PENDING`.


###  Phase 1 — Automation & Local Storage
- [x] Connect to LeetCode GraphQL API
- [x] Automatic workspace/category generation
- [x] SQLite metadata tracking
- [x] Python template generation
- [x] Automated local test case extraction


###  Phase 2 — Behavioral Logging
- [ ] CLI status management (`PENDING`, `SOLVED`, `FAILED`)
- [ ] Duration tracking
- [ ] Submission attempt tracking

---

###  Phase 3 — Resilient Synchronization
- [ ] Detect missing challenge dates
- [ ] Retroactively fetch unsolved daily challenges
- [ ] Prevent historical data gaps


###  Phase 4 — Dockerization
- [ ] Containerize the automation pipeline
- [ ] Persist SQLite database using Docker volumes
- [ ] Reduce dependency on local machine configuration


###  Phase 5 — Cloud Automation
- [ ] Deploy scheduled execution using GitHub Actions
- [ ] Run daily synchronization automatically
- [ ] Keep the database updated without local execution


###  Phase 6 — Analytics & BI Dashboard
- [ ] Connect SQLite data to Power BI
- [ ] Track solving consistency
- [ ] Analyze topic proficiency
- [ ] Measure average solving time by difficulty
- [ ] Build long-term learning analytics

If you wanna see the results of this repository, check it on: https://github.com/Dev-Yudii/leetcode
