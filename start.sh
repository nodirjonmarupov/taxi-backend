#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║          TAXI BACKEND - QUICK START                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

if [ ! -f .env ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "⚠️  Edit .env and set TELEGRAM_BOT_TOKEN"
    read -p "Press Enter after setting token..."
fi

echo "🚀 Starting services..."
docker-compose up -d

echo "⏳ Waiting for services..."
sleep 10

echo "✅ System Ready!"
echo ""
echo "🌐 API:     http://localhost:8000"
echo "📚 Docs:    http://localhost:8000/docs"
echo "🧪 Test:    python test_api.py"
echo "📋 Logs:    docker-compose logs -f"
echo "🛑 Stop:    docker-compose down"
