#!/bin/bash
# Helper script for NAATools development mode
# Starts containers with local NAATools mounted for live development

set -e

echo "============================================"
echo "Starting NA-ACCORD with NAATools Dev Mode"
echo "============================================"
echo ""
echo "This will mount your local NAATools directory:"
echo "  /Users/erikwestlund/code/NAATools"
echo ""
echo "Changes to NAATools will be reflected immediately"
echo "without needing to rebuild containers."
echo ""

# Restart services with NAATools dev override
docker compose -f docker-compose.yml -f docker-compose.naatools-dev.yml up -d services celery flower

echo ""
echo "✓ Services restarted in NAATools dev mode"
echo ""
echo "To return to normal mode (installed NAATools):"
echo "  docker compose up -d services celery flower"
echo ""
