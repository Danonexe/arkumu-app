#!/bin/bash

# Clear all Huey tasks and reset the development environment
# This script stops all containers, clears Redis data, and restarts everything

echo "🧹 Clearing all Huey tasks and resetting development environment..."

# Stop all containers
echo "⏹️  Stopping all containers..."
docker compose -f docker-compose.local.yml down

# Remove Redis volume to clear all task data
echo "🗑️  Clearing Redis data (all tasks will be removed)..."
docker volume rm arkumu-app_arkumu_local_redis_data 2>/dev/null || echo "Redis volume was already removed"

# Clear Django cache as well
echo "🧹 Clearing Django cache..."
docker volume rm arkumu-app_arkumu_local_django_cache 2>/dev/null || echo "Django cache volume doesn't exist"

# Restart all containers
echo "🚀 Starting all containers with fresh state..."
docker compose -f docker-compose.local.yml up -d

echo "✅ All tasks cleared! Environment reset complete."
echo "🎯 You can now start fresh imports without any stale tasks."