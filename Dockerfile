FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jarvis/ jarvis/

# Persistent state (portfolio, journal, equity history, chat) lives here —
# mount a volume over it.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# Binding 0.0.0.0 inside the container; set JARVIS_DASHBOARD_TOKEN before
# publishing the port anywhere non-local.
CMD ["python", "-m", "jarvis", "dashboard", "--host", "0.0.0.0", "--port", "8000"]
