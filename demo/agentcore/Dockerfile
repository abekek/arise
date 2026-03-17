FROM --platform=linux/arm64 python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ARISE from PyPI
RUN pip install --no-cache-dir arise-ai>=0.1.0

COPY . .

EXPOSE 9000

CMD ["python", "agent.py"]
