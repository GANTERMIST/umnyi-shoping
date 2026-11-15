@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Умный Шопинг: установка зависимостей (один раз), сборка фронтенда и запуск сервера
python -m pip install -q -r requirements.txt
if not exist frontend\dist\index.html (
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
)
if not exist data\shop.db (
  echo Первый запуск: загружаю цены 20 популярных игр в фоне...
  start "Загрузчик цен" /min python -m app.loader --top 20
)
start "" http://127.0.0.1:8790/
python -m uvicorn app.main:app --port 8790
