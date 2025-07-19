#!/bin/bash

# Simple reset: Stop and restart containers
# Redis will automatically clear all tasks on startup
echo "🔥 RESETTING CONTAINERS - All tasks will be cleared automatically"

# Stop all containers
echo "⏹️  Stopping containers..."
docker compose -f docker-compose.local.yml down

# Start containers (Redis will auto-clear on startup)
echo "🚀 Starting containers..."
docker compose -f docker-compose.local.yml up -d

echo "✅ DONE! Redis auto-cleared all tasks on startup."