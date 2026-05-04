@echo off
title Stop Unified Trading Dashboard
echo Stopping Streamlit app running on port 8501...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501') do (
    taskkill /F /PID %%a
)
echo App stopped.
pause
