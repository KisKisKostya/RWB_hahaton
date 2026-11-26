# RWB Mesh

Панель управления ПВЗ и Mesh-доставкой: React/Vite frontend и FastAPI backend.

## Быстрый запуск через Docker

Требуется установленный **Docker Desktop** с включённым Docker Compose.

1. Склонируйте репозиторий и перейдите в его корневую папку.
2. При необходимости скопируйте пример переменных окружения:

   ```powershell
   copy .env.example .env
   ```

3. Соберите образы и запустите приложение:

   ```powershell
   docker compose up --build -d
   ```

4. Откройте в браузере:

   - Frontend: http://localhost:8080
   - API документация: http://localhost:8080/api/docs
   - Health check backend: http://localhost:8080/api/health

Frontend обслуживается Nginx. Запросы с префиксом `/api` проксируются в FastAPI. Backend не публикуется напрямую на хост.

## Полезные команды

Посмотреть состояние контейнеров:

```powershell
docker compose ps
```

Посмотреть логи всех сервисов:

```powershell
docker compose logs -f
```

Посмотреть логи только backend:

```powershell
docker compose logs -f backend
```

Остановить контейнеры, сохранив данные:

```powershell
docker compose down
```

Пересобрать образы после изменений в коде:

```powershell
docker compose up --build -d
```

Остановить контейнеры и **удалить базу данных**:

```powershell
docker compose down -v
```

> Внимание: команда с `-v` удаляет именованный volume с SQLite базой. Не используйте её, если хотите сохранить данные.

## Хранение данных

По умолчанию SQLite находится в именованном Docker volume `mesh_data` по пути `/data/mesh.db` внутри backend-контейнера. Пересоздание контейнера не удаляет этот volume.

Для изменения адреса базы данных задайте `DATABASE_URL` в файле `.env`. Текущая конфигурация проекта рассчитана на SQLite.

## Демонстрационные данные

При первом запуске backend создаёт таблицы автоматически, но **не запускает seed-скрипт**. Новая база будет пустой.

В проекте есть `python -m app.seed`, но этот скрипт очищает существующие таблицы перед заполнением демоданными. Не запускайте его на базе с нужными данными.

## Локальная разработка без Docker

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend в отдельном терминале:

```powershell
cd frontend/pvz
npm ci
npm run dev
```

В режиме Vite запросы `/api` автоматически проксируются на `http://127.0.0.1:8000`.

## Архитектура

- `frontend`: React 19, TypeScript, Vite.
- `frontend/pvz/nginx.conf`: раздача SPA и reverse proxy для API.
- `backend`: FastAPI, SQLAlchemy, SQLite.
- `docker-compose.yml`: запуск frontend и backend, health checks и постоянное хранилище БД.
