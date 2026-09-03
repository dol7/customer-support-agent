FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src

# Pass ANTHROPIC_API_KEY at run time; append the customer message as the CMD args:
#   docker run --rm -e ANTHROPIC_API_KEY maven-claude-cert "status of ORD-456"
ENTRYPOINT ["python", "-m", "support_agent"]
