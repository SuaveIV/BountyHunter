FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy source
COPY src ./src
ENV PYTHONPATH=/app/src
ENV DATABASE_PATH=/app/data/bountyhunter.db
VOLUME /app/data
CMD ["python", "-m", "bounty_discord.run"]