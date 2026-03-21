# ARISE Examples

## Getting Started

```bash
pip install arise-ai[litellm]
export OPENAI_API_KEY=sk-...
```

## Examples

| Example | Description |
|---------|-------------|
| [quickstart.py](quickstart.py) | Math agent starts with `add`/`multiply`, evolves `average`, `factorial`, `std_dev` as tasks demand them. Best starting point. |
| [quickstart_evolution.py](quickstart_evolution.py) | Minimal ~50-line demo of the full evolution loop: agent fails at SHA-256 hashing, ARISE synthesizes `compute_sha256`, agent succeeds. |
| [coding_agent.py](coding_agent.py) | Agent with file read/write and shell tools tackles code manipulation tasks, evolving new tools as needed. |
| [data_analysis_agent.py](data_analysis_agent.py) | Agent starts with CSV reader and pandas tools, evolves specialized analysis tools for anomaly detection, correlation, and statistics. |
| [api_agent.py](api_agent.py) | Mock REST API server with auth, pagination, and rate limiting. Agent evolves from bare `http_get`/`http_post` to specialized API tools. |
| [devops_agent.py](devops_agent.py) | Agent handles 10 real-world DevOps tasks (log parsing, metrics, config management) evolving tools along the way. |
| [file_gen_agent.py](file_gen_agent.py) | Uses OpenAI function calling for file generation across formats (JSON, YAML, DOCX, HTML), evolving format conversion tools. |
| [retrieval_agent.py](retrieval_agent.py) | Lightweight agent with text search and regex tools for retrieval and analysis tasks. |
| [strands_agent.py](strands_agent.py) | ARISE wrapping a native Strands agent (Claude Haiku via Bedrock) with composite reward (structural + LLM judge). Requires AWS credentials. |
