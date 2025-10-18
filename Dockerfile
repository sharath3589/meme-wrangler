# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if needed)
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code
COPY bot.py .

# Create directory for database
RUN mkdir -p /app/data

# Set environment variables (will be overridden by docker-compose or run command)
ENV TELEGRAM_BOT_TOKEN=""
ENV OWNER_ID=""
ENV CHANNEL_ID=""
ENV MEMEBOT_DB="/app/data/memes.db"

# Run the bot
CMD ["python", "bot.py"]
