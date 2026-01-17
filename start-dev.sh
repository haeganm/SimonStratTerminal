#!/bin/bash
# Start both backend and frontend development servers
# Usage: ./start-dev.sh

echo "Starting Simons Trading System..."
echo ""

# Check if backend is already running
if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "Backend is already running!"
else
    echo "Starting backend server..."
    cd backend
    python -m app.cli serve &
    BACKEND_PID=$!
    cd ..
    
    # Wait for backend to be ready
    max_attempts=10
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
            echo "Backend is ready!"
            break
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    if [ $attempt -eq $max_attempts ]; then
        echo "Warning: Backend may not be ready yet"
    fi
fi

echo ""
echo "Starting frontend server..."
cd signal-compass

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo ""
echo "========================================"
echo "Backend:  http://127.0.0.1:8000"
echo "Frontend: http://localhost:8080"
echo "API Docs:  http://127.0.0.1:8000/docs"
echo "========================================"
echo ""

# Start frontend (this will block)
npm run dev
