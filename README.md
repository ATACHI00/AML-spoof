# AML Monitor

**Anti-Money Laundering Transaction Monitoring Platform**

платформа для мониторинга транзакций в финтех-компаниях, необанках и платёжных сервисах. Выявляет подозрительные операции в соответствии с AML-требованиями (AMLD5/6, BSA/FinCEN, 115-ФЗ).

---

## Быстрый старт (ручной режим)

### 1. Установите зависимости

```bash
cd aml/backend
poetry install
```

### 2. Настройте окружение

Скопируйте `.env.example` в `.env` и настройте параметры:

```env
DATABASE_URL=sqlite+aiosqlite:///./backend/aml_monitor.db
DATABASE_URL_SYNC=sqlite:///./backend/aml_monitor.db
REDIS_URL=redis://localhost:6379/0
API_KEYS=dev-api-key-1,dev-api-key-2
```

### 3. Запустите миграции базы данных

```bash
poetry run alembic upgrade head
```

### 4. Запустите Backend (FastAPI)

```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Запустите Frontend (Next.js)

```bash
cd ../frontend
npm run dev
```

### 6. Запустите Celery Worker (обязательно!)

```bash
cd ../backend
poetry run celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

> **Важно для Windows:** Используйте `--pool=solo`, иначе Celery не запустится.

---

## Быстрый старт (Docker Compose)

```bash
cd aml
docker compose up --build
```

После запуска:
- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000
- **Swagger docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Как остановить сервисы

### Ручной режим
Нажмите `Ctrl+C` в каждом терминале, где запущен процесс (backend, frontend, worker).

### Docker Compose
```bash
docker compose down
```

### Остановить все процессы Python/Node
```bash
taskkill //F //IM python.exe //IM node.exe
```

---

## Как работает мониторинг

### 1. Блокчейн polling (Celery beat)
Каждые 5 минут Celery запускает задачи:
- `poll_bitcoin_chain` — скачивает транзакции из Bitcoin
- `poll_ethereum_chain` — скачивает транзакции из Ethereum
- `poll_usdt_chain` — скачивает USDT (ERC20/TRC20)
- `poll_monero_chain` — скачивает транзакции из Monero

### 2. Детекторы правил
Каждая транзакция проверяется на 9 типов аномалий:

| Детектор | Описание |
|----------|----------|
| `structuring` | Smurfing — несколько транзакций чуть ниже лимита |
| `rapid_movement` | Быстрое движение средств (вход → выход за 60 мин) |
| `round_amount` | Подозрительно круглые суммы (5000, 10000 и т.д.) |
| `velocity` | Высокая частота транзакций (>10 за час) |
| `geographic` | Транзакции из высокорисковых юрисдикций |
| `dormant` | Активность на "спящих" счетах (90+ дней без活动) |
| `sanctions_match` | Проверка на OFAC/EU/UN списки |
| `ml_anomaly` | ML-детекция (Isolation Forest) |
| `graph_anomaly` | Циклы и подозрительные кластеры в графе |

### 3. Создание алертов
Если детектор срабатывает, создаётся алерт со:
- Severity: `low` / `medium` / `high` / `critical`
- Risk score: от 0 до 100
- Описание проблемы
  
---

## Структура проекта

```
aml/
├── backend/
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   ├── models/       # Модели БД (Transaction, Alert, Rule и т.д.)
│   │   ├── schemas/      # Pydantic схемы
│   │   ├── services/     # Бизнес-логика (rule_engine, blockchain_client)
│   │   ├── workers/      # Celery задачи
│   │   └── utils/        # Утилиты
│   ├── tests/            # Тесты
│   └── alembic/          # Миграции БД
├── frontend/
│   └── src/
│       └── app/          # Страницы Next.js
└── docker-compose.yml
```

---

## Недоработанные функции

### Высокий приоритет
- [ ] Правильная работа Celery beat на Windows (требует `--pool=solo`)
- [ ] Автоматическое притягивание транзакций из блокчейнов (работает, но без beat)
- [ ] Пагинация в list_transactions API

### Средний приоритет
- [ ] UI для управления правилами (CRUD через веб)
- [ ] Auth UI (страница логина для compliance-офицеров)
- [ ] Редактирование клиентов/аккаунтов

### Низкий приоритет
- [ ] Отчётность в PDF
- [ ] WebSocket для real-time алертов
- [ ] Интеграция с Telegram/Slack для уведомлений

---

## Часто задаваемые вопросы

**Q: Почему алерты не создаются?**
A: Проверьте, запущен ли `Celery Worker`. Без него блокчейн polling не работает.

**Q: Как проверить, что сервис работает?**
A: Зайдите на http://localhost:8000/health — должно быть `{"status":"ok"}`

**Q: Где хранятся данные?**
A: По умолчанию — в `aml_monitor.db` (SQLite). В Docker — в PostgreSQL.

**Q: Как сбросить базу данных?**
A: Удалите `aml_monitor.db` и запустите `alembic upgrade head` снова.

---

## Лицензия

MIT — для демонстрационных целей. Не для продакшн-использования без соответствующей сертификации.
