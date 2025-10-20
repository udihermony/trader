#!/bin/bash

# Quick start script for AlgoTrader

echo "🚀 Starting AlgoTrader..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp env.example .env
    echo "⚠️  Please edit .env file with your actual configuration before continuing."
    echo "Press Enter when ready..."
    read
fi

# Start services
echo "🐳 Starting services with Docker Compose..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services are running!"
    echo ""
    echo "📊 Application URLs:"
    echo "   - API: http://localhost:8000"
    echo "   - Docs: http://localhost:8000/docs"
    echo "   - Health: http://localhost:8000/api/v1/health/"
    echo ""
    echo "🔧 Useful commands:"
    echo "   - View logs: docker-compose logs -f"
    echo "   - Stop services: docker-compose down"
    echo "   - Restart: docker-compose restart"
    echo ""
    echo "📚 Next steps:"
    echo "   1. Register a user: POST /api/v1/auth/register"
    echo "   2. Login: POST /api/v1/auth/login"
    echo "   3. Get Fyers auth URL: GET /api/v1/auth/fyers/auth-url"
    echo "   4. Create a strategy: POST /api/v1/strategies/"
    echo "   5. Test webhook: POST /api/v1/webhooks/test-signal"
else
    echo "❌ Some services failed to start. Check logs with: docker-compose logs"
    exit 1
fi
