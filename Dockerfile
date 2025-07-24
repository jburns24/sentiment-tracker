FROM python:3.13-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY src ./src

# Set PYTHONPATH to allow imports from src
ENV PYTHONPATH=/app

# Run the application
CMD ["python", "-m", "src.main"]
