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


## Future Roadmap & Goals
I plan to evolve this project incrementally as I study:

* **[x] Phase 1: Local Automation Script & Storage (MVP - Completed)**
  * Established communication with LeetCode's GraphQL API to extract the daily metadata and code structures.
  * Developed dynamic workspace separation using Python's `os` and `re` libraries to organize problem categories automatically.
  * Designed a local schema using SQLite to log basic information (`id`, `title`, `slug`, `link`, `difficulty`, `date`, `category`).
  * Created an immutable template generator to inject automated syntax-ready test execution blocks in each script.

* **[ ] Phase 2: Behavioral Logging**
  * Create a terminal script to mark a problem as `SOLVED` or `FAILED`.
  * Implement tracking metrics: some way to input duration (time spent) and number of submission attempts.

* **[ ] Phase 3: Resilient Synchronization (Anti-Gap Logic)**
  * Update the script to check the last recorded date in the database. If I miss a few days without turning on my PC, the script will fetch the missing daily challenges retroactively to avoid gaps in my historical data.

* **[ ] Phase 4: Dockerization**
  * Envelop the execution pipeline into a Docker container to decouple the script from my local machine configuration, using Docker Volumes to store the database file safely on the host machine. (I recently started learning about Docker, and I'm eager to use more of this technology).

* **[ ] Phase 5: Cloud Automation (Hands-off Pipeline)**
  * Deploy the Docker container to **GitHub Actions** with a CRON trigger. The script will run automatically on the cloud every night at 9:00 PM (when LeetCode resets), keeping my database updated even if my computer is turned off.

* **[ ] Phase 6: Analytics & BI Dashboard**
  * Connect the accumulated SQLite data into a BI tool (Most likely Power BI because it's another tool I'm studying) to analyze metrics like *Average Time Spent per Difficulty*, *Topic Proficiency*, and *Technical Debt Repayment Rate* (how fast I catch up on missed days).

If you wanna see the results of this repository, check it on: https://github.com/Dev-Yudii/leetcode
