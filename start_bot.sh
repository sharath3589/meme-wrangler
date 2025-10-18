#!/bin/bash

# Meme Wrangler Bot Startup Script
# Double-click this file to start your bot

cd /Users/hyperterminal/myspace/meme-wrangler
source .venv/bin/activate

# Set your credentials here (replace with your actual values)
export TELEGRAM_BOT_TOKEN="8478225179:AAH_38KkQHPEnIcacUzCs8M-VDkBGfxR3UA"
export OWNER_ID="324460662"
export CHANNEL_ID="@meme_galore"

# Start the bot
echo "Starting Meme Wrangler Bot..."
python3 bot.py
