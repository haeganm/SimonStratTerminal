# Start both backend and frontend development servers
# Usage: .\start-dev.ps1

Write-Host "Starting Simons Trading System..." -ForegroundColor Green
Write-Host ""

# Check if backend is already running
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "Backend is already running!" -ForegroundColor Yellow
} catch {
    Write-Host "Starting backend server..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; python -m app.cli serve" -WindowStyle Normal
    Start-Sleep -Seconds 3
    
    # Wait for backend to be ready
    $maxAttempts = 10
    $attempt = 0
    while ($attempt -lt $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            Write-Host "Backend is ready!" -ForegroundColor Green
            break
        } catch {
            $attempt++
            Start-Sleep -Seconds 1
        }
    }
    
    if ($attempt -eq $maxAttempts) {
        Write-Host "Warning: Backend may not be ready yet" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Starting frontend server..." -ForegroundColor Cyan
Set-Location signal-compass

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Backend:  http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:8080" -ForegroundColor Cyan
Write-Host "API Docs:  http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Start frontend (this will block)
npm run dev
