@echo off
cd /d C:\Users\GREEN-SRV03\PROJETO-FERIAS\ferias-app
call .\.venv\Scripts\activate
python -m streamlit run admin_app.py
pause
