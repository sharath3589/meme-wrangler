# Memebot

Telegram bot that accepts memes (photos, GIF animations, videos) from the owner's private messages and schedules them into a channel at the next available slot among 11:00, 16:00, 21:00.

Setup

1. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables:

```
export TELEGRAM_BOT_TOKEN=123:ABC
export OWNER_ID=123456789
export CHANNEL_ID=@yourchannel or -1001234567890
```

3. Run the bot:

```bash
python bot.py
```

How it works

-   Owner sends a photo/video/animation in the bot's DM.
-   Bot stores the Telegram file_id and schedules it for the next available slot: 11:00, 16:00, 21:00. If there's an existing scheduled meme, new ones are scheduled after the last one using the same cycle.
-   A background task posts due memes into the configured channel.

Notes

-   Times are computed using server local time. Stored timestamps are Unix timestamps.
-   Make sure the bot is admin in the channel to post messages.
