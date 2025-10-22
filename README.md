# Meme Wrangler Bot

Telegram bot that accepts memes (photos, GIF animations, videos) from the owner's private messages and schedules them into a channel at the next available slot among 11:00, 16:00, 21:00.

## Setup

### Option 1: Run with Docker (Recommended)

The easiest way to run the bot is using Docker:

1. **Set up environment variables:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your bot credentials
   ```

2. **Run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

3. **View logs:**
   ```bash
   docker-compose logs -f
   ```

4. **Stop the bot:**
   ```bash
   docker-compose down
   ```

For detailed Docker deployment instructions, including remote server deployment, see [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md).

### Option 2: Run Locally

1. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables:

```bash
export TELEGRAM_BOT_TOKEN=123:ABC
export OWNER_ID=123456789
export CHANNEL_ID=@yourchannel  # or -1001234567890
```

3. Run the bot:

```bash
python bot.py
```

## How it works

-   Owner sends a photo/video/animation in the bot's DM.
-   Bot stores the Telegram file_id and schedules it for the next available slot: **11:00, 16:00, 21:00 IST (India Standard Time)**. If there's an existing scheduled meme, new ones are scheduled after the last one using the same cycle.
-   A background task posts due memes into the configured channel at the scheduled IST times.

## Docker Implementation

This project includes full Docker support for easy deployment:

- **Dockerfile**: Creates a lightweight Python container with all dependencies
- **docker-compose.yml**: Simplifies running the bot with proper configuration
- **Volume mounting**: Database persists between container restarts in `./data` directory
- **Auto-restart**: Container automatically restarts if it crashes
- **Logging**: Configured with log rotation (10MB max, 3 files)

The Docker implementation ensures consistent behavior across different environments and simplifies deployment to production servers.

## Notes

-   All times are in **IST (India Standard Time, UTC+5:30)** regardless of the server's timezone.
-   Stored timestamps are Unix timestamps (UTC).
-   Make sure the bot is admin in the channel to post messages.
-   When using Docker, the database is stored in `./data/memes.db` on the host machine.
