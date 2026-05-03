@echo off
title Unified Trading Strategy Dashboard

echo Installing required packages...
"C:\Users\nelko\AppData\Local\Programs\Python\Python313\python.exe" -m pip install -r requirements.txt

echo Starting Unified Trading Strategy Dashboard...
"C:\Users\nelko\AppData\Local\Programs\Python\Python313\python.exe" -m streamlit run app.py

pause
