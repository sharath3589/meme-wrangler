# Meme Wrangler Bot - Docker Deployment Guide

This guide covers how to run your Telegram Meme Wrangler Bot using Docker.

## Prerequisites

- Docker installed on your system
- Docker Compose installed (usually comes with Docker Desktop)
- Your bot token, owner ID, and channel ID

### Installing Docker

**On macOS:**
```bash
brew install --cask docker
# Or download Docker Desktop from https://www.docker.com/products/docker-desktop
```

**On Linux (Ubuntu/Debian):**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Add your user to docker group (to run without sudo)
sudo usermod -aG docker $USER
# Log out and back in for this to take effect
```

## Quick Start

### 1. Set Up Environment Variables

Copy the example file and edit it:

```bash
cp .env.example .env
nano .env  # or use any text editor
```

Fill in your actual values:
```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
OWNER_ID=987654321
CHANNEL_ID=@yourchannel
```

### 2. Build and Run with Docker Compose (Easiest)

```bash
# Build and start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down

# Restart the bot
docker-compose restart
```

That's it! Your bot is now running in Docker! 🎉

## Alternative: Using Docker Commands Directly

### Build the Image

```bash
docker build -t meme-wrangler .
```

### Run the Container

```bash
# Create data directory for database persistence
mkdir -p ./data

# Run the bot (replace with your actual values)
docker run -d \
  --name meme-wrangler \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="your_token_here" \
  -e OWNER_ID="your_id_here" \
  -e CHANNEL_ID="@your_channel" \
  -v $(pwd)/data:/app/data \
  meme-wrangler
```

### Manage the Container

```bash
# View logs
docker logs -f meme-wrangler

# Stop the bot
docker stop meme-wrangler

# Start the bot
docker start meme-wrangler

# Restart the bot
docker restart meme-wrangler

# Remove the container
docker rm -f meme-wrangler

# View container status
docker ps -a
```

## Deploying to a Remote Server

### Option 1: Copy Files and Build on Server

```bash
# From your Mac, copy files to server
scp -i /path/to/ssh_key -r \
  /Users/hyperterminal/myspace/meme-wrangler \
  username@server_ip:~/

# SSH into server
ssh -i /path/to/ssh_key username@server_ip

# Navigate to bot directory
cd ~/meme-wrangler

# Create .env file
cp .env.example .env
nano .env  # Fill in your credentials

# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Option 2: Build Locally and Push to Registry

```bash
# Tag the image
docker tag meme-wrangler yourusername/meme-wrangler:latest

# Push to Docker Hub (requires docker login)
docker push yourusername/meme-wrangler:latest

# On the server, pull and run
docker pull yourusername/meme-wrangler:latest
docker run -d \
  --name meme-wrangler \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e OWNER_ID="your_id" \
  -e CHANNEL_ID="@channel" \
  -v ~/meme-wrangler-data:/app/data \
  yourusername/meme-wrangler:latest
```

## Updating the Bot

### If using Docker Compose:

```bash
# Make your code changes, then:
docker-compose down
docker-compose build
docker-compose up -d
```

### If using Docker commands:

```bash
# Stop and remove old container
docker stop meme-wrangler
docker rm meme-wrangler

# Rebuild image
docker build -t meme-wrangler .

# Run new container
docker run -d \
  --name meme-wrangler \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="your_token" \
  -e OWNER_ID="your_id" \
  -e CHANNEL_ID="@channel" \
  -v $(pwd)/data:/app/data \
  meme-wrangler
```

## Data Persistence

The database file (`memes.db`) is stored in the `./data` directory on your host machine, which is mounted as a volume in the container. This means:

- ✅ Your scheduled memes persist even if you stop/restart the container
- ✅ You can backup the database by copying the `./data` folder
- ✅ You can inspect the database from your host machine

## Troubleshooting

### Check if container is running:
```bash
docker ps
```

### View logs:
```bash
# Docker Compose
docker-compose logs -f

# Docker command
docker logs -f meme-wrangler
```

### Access container shell:
```bash
# Docker Compose
docker-compose exec meme-wrangler /bin/bash

# Docker command
docker exec -it meme-wrangler /bin/bash
```

### Container keeps restarting:
```bash
# Check logs for errors
docker logs memebot

# Common issues:
# 1. Missing environment variables
# 2. Invalid bot token
# 3. Database permission issues
```

### Remove everything and start fresh:
```bash
docker-compose down -v  # Removes containers and volumes
docker system prune -a  # Clean up Docker system (optional)
```

## Benefits of Docker

- ✅ **Consistent environment**: Works the same everywhere
- ✅ **Easy deployment**: Just copy files and run
- ✅ **Isolation**: Doesn't interfere with system Python
- ✅ **Easy updates**: Just rebuild and restart
- ✅ **Portability**: Move between servers easily
- ✅ **Auto-restart**: Container restarts automatically if it crashes

## Docker on Friend's Server

When your friend gives you SSH access:

```bash
# 1. Connect to server
ssh -i /path/to/key username@server_ip

# 2. Install Docker (if not installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt install docker-compose-plugin -y

# 3. Create bot directory
mkdir -p ~/memebot
cd ~/memebot

# 4. Exit SSH and upload files from your Mac
exit
scp -i /path/to/key -r \
  /Users/hyperterminal/myspace/memebot/* \
  username@server_ip:~/memebot/

# 5. SSH back and run
ssh -i /path/to/key username@server_ip
cd ~/memebot

# Create .env file
nano .env  # Add your credentials

# Run with Docker Compose
docker-compose up -d

# Check it's working
docker-compose logs -f
```

Done! Your bot runs 24/7 automatically! 🚀
