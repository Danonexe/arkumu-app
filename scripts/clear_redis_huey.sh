#!/bin/bash
#
# Emergency Redis cleanup script for Huey task queue
# 
# This script clears the Redis database used by Huey to remove
# stale tasks and resolve registry errors.
#
# Usage:
#   ./scripts/clear_redis_huey.sh
#   ./scripts/clear_redis_huey.sh --force
#

set -e

FORCE=${1:-""}

echo "🔴 Huey Redis Cleanup Script"
echo "=================================="

# Check if docker-compose is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

# Check if docker-compose.local.yml exists
if [ ! -f "docker-compose.local.yml" ]; then
    echo "❌ docker-compose.local.yml not found. Are you in the project root?"
    exit 1
fi

echo "📋 This script will:"
echo "   - Clear all Huey task queues from Redis"
echo "   - Remove stale task references"
echo "   - Resolve registry errors"
echo ""

if [ "$FORCE" != "--force" ]; then
    read -p "⚠️  Are you sure you want to continue? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Operation cancelled."
        exit 1
    fi
fi

echo "🚀 Starting Redis cleanup..."

# Start Redis if not running
echo "📡 Ensuring Redis is running..."
docker compose -f docker-compose.local.yml up -d redis

# Wait for Redis to be ready
echo "⏳ Waiting for Redis to be ready..."
sleep 2

# Clear all Redis databases
echo "🧹 Clearing Redis databases..."
docker compose -f docker-compose.local.yml exec redis redis-cli FLUSHALL

# Check if cleared
echo "✅ Verifying Redis is clean..."
KEYCOUNT=$(docker compose -f docker-compose.local.yml exec redis redis-cli DBSIZE)
echo "   Redis keys remaining: $KEYCOUNT"

echo ""
echo "🎉 Redis cleanup completed successfully!"
echo ""
echo "📝 Next steps:"
echo "   1. Restart your Huey consumer:"
echo "      docker compose -f docker-compose.local.yml restart huey"
echo ""
echo "   2. Or use the Django management command:"
echo "      docker compose -f docker-compose.local.yml run --rm django python manage.py clear_huey_queue"
echo ""
echo "   3. Check that your tasks are now registering properly"
echo ""