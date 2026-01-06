#!/bin/bash
# Smart healthcheck for services container
# Adapts based on SERVICE_TYPE environment variable

set -e

case "${SERVICE_TYPE:-services}" in
    services)
        # Django web service - check HTTP endpoint
        python -c "import requests; requests.get('http://localhost:8001/health/', timeout=5)" || exit 1
        ;;
    celery)
        # Celery worker - check if worker processes are running
        # Use python to check process list since pgrep/ps might not be available
        python -c "
import os
import sys

# Check if any process contains 'celery' and 'worker' in command line
proc_dir = '/proc'
found = False

for pid in os.listdir(proc_dir):
    if not pid.isdigit():
        continue
    try:
        cmdline_path = os.path.join(proc_dir, pid, 'cmdline')
        with open(cmdline_path, 'rb') as f:
            cmdline = f.read().decode('utf-8', errors='ignore').replace('\x00', ' ')
            if 'celery' in cmdline.lower() and 'worker' in cmdline.lower():
                found = True
                break
    except:
        continue

sys.exit(0 if found else 1)
" || exit 1
        ;;
    celery-beat)
        # Celery beat - check if beat process is running
        python -c "
import os
import sys

# Check if any process contains 'celery' and 'beat' in command line
proc_dir = '/proc'
found = False

for pid in os.listdir(proc_dir):
    if not pid.isdigit():
        continue
    try:
        cmdline_path = os.path.join(proc_dir, pid, 'cmdline')
        with open(cmdline_path, 'rb') as f:
            cmdline = f.read().decode('utf-8', errors='ignore').replace('\x00', ' ')
            if 'celery' in cmdline.lower() and 'beat' in cmdline.lower():
                found = True
                break
    except:
        continue

sys.exit(0 if found else 1)
" || exit 1
        ;;
    *)
        echo "Unknown SERVICE_TYPE: ${SERVICE_TYPE}"
        exit 1
        ;;
esac

exit 0
