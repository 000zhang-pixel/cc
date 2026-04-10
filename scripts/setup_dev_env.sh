#!/bin/bash
# Setup development environment for AI-Content-Hub

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MIDDLEWARE_DIR="$PROJECT_ROOT/middleware"

echo "🚀 Setting up AI-Content-Hub development environment..."

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "📍 Python version: $PYTHON_VERSION"

# Create virtual environment
echo "📦 Creating virtual environment..."
cd "$MIDDLEWARE_DIR"
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating project directories..."
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/content-store"
mkdir -p "$PROJECT_ROOT/content-store/inbox"
mkdir -p "$PROJECT_ROOT/content-store/Pending_Content"
mkdir -p "$PROJECT_ROOT/content-store/archive"
mkdir -p "$PROJECT_ROOT/data"

# Check for .env file
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "⚠️  .env file not found!"
    echo "📝 Please copy .env.example and fill in your credentials:"
    echo "   cp $PROJECT_ROOT/.env.example $PROJECT_ROOT/.env"
    echo ""
    echo "🔑 Required environment variables:"
    echo "   - LARK_APP_ID"
    echo "   - LARK_APP_SECRET"
    echo "   - LARK_BASE_TOKEN"
    echo "   - OPENAI_API_KEY or KIMI_API_KEY"
    echo "   - LOCAL_STORAGE_ROOT"
else
    echo "✅ .env file exists"
fi

echo ""
echo "✨ Development environment setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env file with your credentials"
echo "  2. Run database migrations: cd middleware && python -m alembic upgrade head"
echo "  3. Start the middleware: cd middleware && python main.py"
