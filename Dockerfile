FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the project in editable mode (or standard) so imports work correctly
RUN pip install .

# Create a directory for the database
RUN mkdir -p data

CMD ["python", "src/bounty_discord/run.py"]