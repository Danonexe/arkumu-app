#!/bin/bash

# Redis initialization script for local development
# This clears all Redis data on container startup to avoid stale Huey tasks

echo "🧹 Initializing Redis for local development..."

# Start Redis in the background
redis-server --appendonly yes --save "" &
REDIS_PID=$!

# Wait for Redis to be ready
echo "⏳ Waiting for Redis to start..."
while ! redis-cli ping > /dev/null 2>&1; do
    sleep 1
done

echo "✅ Redis is ready"

# Clear all existing data (important for development)
echo "🗑️  Clearing all Redis data (development mode)..."
redis-cli FLUSHALL

echo "✅ Redis initialized and cleared for development"

# Keep Redis running in foreground
wait $REDIS_PID