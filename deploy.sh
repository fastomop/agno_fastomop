#!/bin/bash
# FastOMOP Deployment Script
# Automates the deployment process

set -e  # Exit on error

echo "======================================"
echo "FastOMOP Docker Deployment"
echo "======================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found"
    if [ -f .env.docker ]; then
        echo "Creating .env from .env.docker template..."
        cp .env.docker .env
        echo "✓ .env created"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env and update OLLAMA_HOST with your GPU node IP"
        echo "   Run: nano .env"
        echo ""
        read -p "Press Enter after you've configured .env, or Ctrl+C to exit..."
    else
        echo "❌ .env.docker template not found"
        exit 1
    fi
fi

# Verify OLLAMA_HOST is configured
OLLAMA_HOST=$(grep "^OLLAMA_HOST=" .env | cut -d'=' -f2)
if [[ "$OLLAMA_HOST" == *"XXX"* ]] || [ -z "$OLLAMA_HOST" ]; then
    echo "❌ OLLAMA_HOST not configured in .env"
    echo "   Please edit .env and set your GPU node IP"
    exit 1
fi

echo "Configuration:"
echo "  OLLAMA_HOST: $OLLAMA_HOST"
echo ""

# Test Ollama connectivity
echo "Testing Ollama connectivity..."
if curl -s -f "$OLLAMA_HOST/api/tags" > /dev/null 2>&1; then
    echo "✓ Ollama is reachable"
else
    echo "⚠️  Warning: Cannot reach Ollama at $OLLAMA_HOST"
    echo "   Deployment will continue, but FastOMOP may not work"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Create data directory if it doesn't exist
echo "Setting up directories..."
mkdir -p data
echo "✓ Data directory ready"
echo ""

# Build image
echo "Building Docker image..."
docker compose build
echo "✓ Image built"
echo ""

# Start container
echo "Starting container..."
docker compose up -d
echo "✓ Container started"
echo ""

# Wait for startup
echo "Waiting for FastOMOP to start..."
sleep 5

# Check if container is running
if [ "$(docker compose ps -q fastomop)" ]; then
    echo "✓ Container is running"
    echo ""

    # Show logs
    echo "Recent logs:"
    echo "─────────────────────────────────────"
    docker compose logs --tail=20 fastomop
    echo "─────────────────────────────────────"
    echo ""

    # Get server IP
    SERVER_IP=$(hostname -I | awk '{print $1}')

    echo "======================================"
    echo "✓ Deployment Complete!"
    echo "======================================"
    echo ""
    echo "Access FastOMOP at:"
    echo "  • Local: http://localhost:7777"
    echo "  • Network: http://$SERVER_IP:7777"
    echo ""
    echo "Useful commands:"
    echo "  • View logs: docker compose logs -f"
    echo "  • Stop: docker compose down"
    echo "  • Restart: docker compose restart"
    echo "  • Status: docker compose ps"
    echo ""
    echo "Next steps:"
    echo "  1. Bootstrap (first time only):"
    echo "     docker compose exec fastomop python -m agno_fastomop.bootstrap"
    echo ""
    echo "  2. Access web interface at http://$SERVER_IP:7777"
    echo ""
else
    echo "❌ Container failed to start"
    echo ""
    echo "Check logs with: docker compose logs"
    exit 1
fi
