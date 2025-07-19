#!/bin/bash

# Clear only Huey tasks without restarting containers
# This is faster than the full reset but requires Redis to be running

echo "🧹 Clearing Huey tasks..."

# Method 1: Use Django management command
echo "🔧 Attempting to clear tasks via Django management command..."
if docker compose -f docker-compose.local.yml run --rm django python manage.py clear_huey_queue --confirm; then
    echo "✅ Tasks cleared successfully via Django command"
else
    echo "⚠️  Django command failed, trying Redis direct approach..."
    
    # Method 2: Clear Redis directly
    echo "🔧 Clearing Redis keys directly..."
    docker compose -f docker-compose.local.yml exec redis redis-cli FLUSHALL
    
    if [ $? -eq 0 ]; then
        echo "✅ Redis cleared successfully"
    else
        echo "❌ Failed to clear Redis. You may need to use clear_all_tasks.sh instead"
        exit 1
    fi
fi

# Clear Django cache as well
echo "🧹 Clearing Django cache..."
docker compose -f docker-compose.local.yml run --rm django python manage.py clear_cache 2>/dev/null || echo "Cache clearing not available"

echo "✅ Tasks cleared! No restart required."
echo "🎯 You can now start fresh imports."