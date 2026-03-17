"""Sample task set for the ARISE DevOps agent demo.

Each task is a dict with:
    task              str   — the natural-language prompt sent to the agent
    expected_pattern  str   — regex pattern the agent's output must match
                              (used by reward.py to score the trajectory)

Twenty tasks across five capability domains:
    1-4   File parsing        (CSV, JSON)
    5-8   Log analysis        (error extraction, pattern counting)
    9-12  Text processing     (regex, encoding, hashing)
    13-16 Data transformation (sort, filter, aggregate)
    17-20 URL / network data  (URL parsing, query string building)
"""

from __future__ import annotations

TASKS: list[dict[str, str]] = [
    # -----------------------------------------------------------------------
    # Domain 1: File parsing
    # -----------------------------------------------------------------------
    {
        "task": (
            "Parse the following CSV data and return the name and salary of the "
            "highest-paid employee:\n"
            "id,name,salary\n1,Alice,95000\n2,Bob,82000\n3,Charlie,110000\n4,Diana,71000"
        ),
        "expected_pattern": r"(?i)charlie",
    },
    {
        "task": (
            "Given this JSON string, extract the value of 'database.host':\n"
            '{"app": {"name": "myservice"}, "database": {"host": "db.internal.example.com", "port": 5432}}'
        ),
        "expected_pattern": r"db\.internal\.example\.com",
    },
    {
        "task": (
            "Count the number of rows (excluding the header) in this CSV data:\n"
            "id,status,region\n1,active,us-east-1\n2,inactive,us-west-2\n"
            "3,active,eu-west-1\n4,active,ap-southeast-1\n5,inactive,us-east-1"
        ),
        "expected_pattern": r"\b5\b",
    },
    {
        "task": (
            "From the following JSON array, return the names of all services "
            "whose status is 'degraded':\n"
            '[{"name":"api","status":"healthy"},{"name":"worker","status":"degraded"},'
            '{"name":"db","status":"healthy"},{"name":"cache","status":"degraded"}]'
        ),
        "expected_pattern": r"(?i)(worker|cache)",
    },

    # -----------------------------------------------------------------------
    # Domain 2: Log analysis
    # -----------------------------------------------------------------------
    {
        "task": (
            "Count the number of ERROR lines in the following log excerpt:\n"
            "2024-01-01 10:00:01 INFO  Server started\n"
            "2024-01-01 10:01:22 WARN  High memory: 85%\n"
            "2024-01-01 10:02:33 ERROR Connection timeout\n"
            "2024-01-01 10:03:01 INFO  Retry succeeded\n"
            "2024-01-01 10:04:15 ERROR Database lost\n"
            "2024-01-01 10:05:30 ERROR Out of memory\n"
            "2024-01-01 10:06:00 INFO  Health check OK"
        ),
        "expected_pattern": r"\b3\b",
    },
    {
        "task": (
            "Extract all unique IP addresses from this nginx access log:\n"
            '192.168.1.10 - - [01/Jan/2024] "GET /api/users HTTP/1.1" 200 1234\n'
            '10.0.0.5 - - [01/Jan/2024] "GET /api/products HTTP/1.1" 200 5678\n'
            '192.168.1.10 - - [01/Jan/2024] "POST /api/login HTTP/1.1" 200 89\n'
            '172.16.0.3 - - [01/Jan/2024] "GET /api/health HTTP/1.1" 200 12\n'
            '10.0.0.5 - - [01/Jan/2024] "PUT /api/products/1 HTTP/1.1" 500 89'
        ),
        "expected_pattern": r"(?:192\.168\.1\.10|10\.0\.0\.5|172\.16\.0\.3)",
    },
    {
        "task": (
            "From the following application log, list all distinct error messages "
            "(lines containing 'ERROR'):\n"
            "2024-03-01 09:00:00 ERROR Disk quota exceeded\n"
            "2024-03-01 09:00:01 INFO  Cleanup started\n"
            "2024-03-01 09:05:00 ERROR SSL certificate expires in 3 days\n"
            "2024-03-01 09:05:01 WARN  Low disk space\n"
            "2024-03-01 09:10:00 ERROR Disk quota exceeded\n"
            "2024-03-01 09:15:00 INFO  Health check OK"
        ),
        "expected_pattern": r"(?i)(disk quota|ssl certificate)",
    },
    {
        "task": (
            "Analyze this log and return the count of each log level "
            "(DEBUG, INFO, WARN, ERROR):\n"
            "2024-04-01 08:00:00 DEBUG Config loaded\n"
            "2024-04-01 08:00:01 INFO  Service started\n"
            "2024-04-01 08:01:00 INFO  Health check OK\n"
            "2024-04-01 08:02:00 WARN  High latency: 500ms\n"
            "2024-04-01 08:03:00 ERROR Request failed\n"
            "2024-04-01 08:03:01 DEBUG Retry attempt 1\n"
            "2024-04-01 08:03:02 INFO  Request succeeded\n"
            "2024-04-01 08:04:00 ERROR Disk full"
        ),
        "expected_pattern": r"(?i)(debug.*2|info.*3|warn.*1|error.*2)",
    },

    # -----------------------------------------------------------------------
    # Domain 3: Text processing
    # -----------------------------------------------------------------------
    {
        "task": "Compute the SHA-256 hash of the string 'hello world' (lowercase, no newline) and return the hex digest.",
        "expected_pattern": r"b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576[0-9a-f]{8}|"
                            r"b94d27b9934d3e08a52e52d7da7dabfa",
    },
    {
        "task": (
            "Base64-encode the string 'DevOps:password123' and return the encoded value."
        ),
        "expected_pattern": r"RGV2T3BzOnBhc3N3b3JkMTIz",
    },
    {
        "task": (
            "Extract all version strings matching the pattern X.Y.Z from the following text:\n"
            "Deployed flask==2.3.1, requests==2.28.2, gunicorn==20.1.0 to production. "
            "Previous version was flask==2.2.5."
        ),
        "expected_pattern": r"2\.3\.1",
    },
    {
        "task": (
            "Replace all occurrences of 'localhost' with '10.0.0.1' in the following "
            "config snippet and return the updated text:\n"
            "DB_HOST=localhost\nREDIS_HOST=localhost\nAPP_HOST=0.0.0.0\nAPI_URL=http://localhost:8080"
        ),
        "expected_pattern": r"10\.0\.0\.1",
    },

    # -----------------------------------------------------------------------
    # Domain 4: Data transformation
    # -----------------------------------------------------------------------
    {
        "task": (
            "Sort the following list of semantic version strings in descending order "
            "(newest first) and return them as a comma-separated string:\n"
            "1.2.3, 2.0.0, 1.10.1, 0.9.9, 1.2.10, 2.1.0"
        ),
        "expected_pattern": r"2\.1\.0",
    },
    {
        "task": (
            "Filter the following JSON array to keep only records where "
            "'region' is 'us-east-1' and return the filtered list as JSON:\n"
            '[{"id":1,"region":"us-east-1","cost":150},'
            '{"id":2,"region":"eu-west-1","cost":200},'
            '{"id":3,"region":"us-east-1","cost":120},'
            '{"id":4,"region":"ap-southeast-1","cost":180}]'
        ),
        "expected_pattern": r'"region":\s*"us-east-1"',
    },
    {
        "task": (
            "Given the following CSV data, compute the total and average cost per region "
            "and return the result as a JSON object:\n"
            "region,cost\nus-east-1,150\neus-west-1,200\nus-east-1,120\n"
            "ap-southeast-1,180\neus-west-1,90"
        ),
        "expected_pattern": r"(?i)(total|average|avg)",
    },
    {
        "task": (
            "Deduplicate and sort the following list of package names "
            "(case-insensitive, return sorted unique values):\n"
            "Flask, requests, Flask, boto3, REQUESTS, numpy, boto3, Numpy"
        ),
        "expected_pattern": r"(?i)boto3",
    },

    # -----------------------------------------------------------------------
    # Domain 5: URL / network data
    # -----------------------------------------------------------------------
    {
        "task": (
            "Parse the following URL and extract its components (scheme, host, path, "
            "and query parameters):\n"
            "https://api.example.com/v2/users?page=2&limit=50&sort=created_at&order=desc"
        ),
        "expected_pattern": r"(?i)(page|limit|sort|order)",
    },
    {
        "task": (
            "Build a query string from the following parameters dict and append it to "
            "the base URL 'https://api.example.com/search':\n"
            '{"q": "devops tools", "page": 1, "per_page": 20, "lang": "python"}'
        ),
        "expected_pattern": r"https://api\.example\.com/search\?",
    },
    {
        "task": (
            "From the following list of URLs, extract and return only the unique hostnames:\n"
            "https://api.example.com/users\n"
            "https://cdn.example.com/assets/logo.png\n"
            "https://api.example.com/orders\n"
            "https://auth.example.com/login\n"
            "http://cdn.example.com/assets/style.css"
        ),
        "expected_pattern": r"(?:api|cdn|auth)\.example\.com",
    },
    {
        "task": (
            "Validate the following list of IP addresses and classify each as "
            "'private', 'public', or 'invalid':\n"
            "192.168.1.1\n10.0.0.5\n172.31.255.255\n8.8.8.8\n256.1.1.1\n203.0.113.42"
        ),
        "expected_pattern": r"(?i)(private|public|invalid)",
    },
]


if __name__ == "__main__":
    print(f"Task set: {len(TASKS)} tasks")
    for i, t in enumerate(TASKS, 1):
        print(f"\n[{i:02d}] {t['task'][:80]}{'...' if len(t['task']) > 80 else ''}")
        print(f"     pattern: {t['expected_pattern'][:60]}")
