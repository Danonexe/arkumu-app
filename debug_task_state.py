#!/usr/bin/env python3
"""
Debug script to check what's happening with the running task
"""
import os
import sys
import django
import time

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.core.cache import cache
import redis
from django.conf import settings

def debug_task_state():
    print("🔍 Debugging task state...")
    
    # Check Redis connection
    huey_settings = getattr(settings, 'HUEY', {})
    connection_settings = huey_settings.get('connection', {})
    redis_url = connection_settings.get('url')
    
    if redis_url:
        r = redis.from_url(redis_url, decode_responses=True)
    else:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    print(f"📊 Redis connection: {redis_url}")
    
    # Check all Redis keys
    all_keys = r.keys("*")
    print(f"📋 All Redis keys: {all_keys}")
    
    # Check task_state_* keys specifically
    task_state_keys = r.keys("task_state_*")
    print(f"🎯 Task state keys: {task_state_keys}")
    
    # Check Django cache
    print("\n🧠 Django cache contents:")
    for key in all_keys:
        if 'task_state' in key:
            try:
                value = cache.get(key)
                print(f"  {key}: {value}")
            except:
                print(f"  {key}: <error reading value>")
    
    # Check if there are any active tasks
    print(f"\n🔄 Looking for active tasks...")
    
    # Show any keys that might contain the current task ID
    current_task_pattern = "*bcea56d6-2ec6-4570-b72f-21ab644b3276*"
    matching_keys = r.keys(current_task_pattern)
    print(f"🎯 Keys matching current task: {matching_keys}")
    
    for key in matching_keys:
        try:
            value = r.get(key)
            print(f"  {key}: {value}")
        except:
            print(f"  {key}: <error reading value>")

if __name__ == "__main__":
    debug_task_state()