# HANDOFF — повна передача проєкту Aksan Telegram Bot

> Цей документ — головна точка входу для нової сесії / нового акаунта.
> Тут зібрано: що це за проєкт, що зроблено, що ще треба, і **детально** як усе
> запускати локально та деплоїти на сервер (з точними командами).
>
> Дата останнього оновлення: **2026-06-10**. Гілка: `main`.
> Репозиторій: **https://github.com/MaxSaiets/Aksan_telegram_bot**

---

## 0. TL;DR (найкоротше)

- Це Telegram-бот для магазину одягу **Aksan**. Обробляє відео/фото товарів,
  заливає відео на YouTube, шле оброблену медіа в Telegram-групу, і **генерує
  Excel-файли** для Rozetka / сайту / SalesDrive CRM.
- Стек: **Python 3.11 + FastAPI + aiogram v3 + Celery + Redis + Supabase + FFmpeg**.
- Робочий режим у проді — **polling** (не webhook).
- Деплой — **git push у `main` → GitHub Actions (self-hosted Windows runner) →
  `deploy.ps1`** на сервері. Жодного ручного SSH не треба.
- Локальний робочий каталог цього клону: `D:\Aksan_tel_bot`.
- Прод-каталог на сервері: `C:\bots\telegram_aksan_bot`.

---

## 1. Що вміє бот (меню «📁 Отримати файли» + основні потоки)

Reply-клавіатура (головне меню) — [app/telegram/keyboard.py](../app/telegram/keyboard.py):

| Кнопка | Дія |
|---|---|
| 📤 Відправити відео | прийняти відео з підписом → YouTube + overlay → група |
| 📸 Додати фото | прийняти багато фото → стиснути в JPG 600×900 → група |
| 🗑 Видалити попереднє фото | прибрати останній батч фото |
| ↩️ Скасувати останнє відео | видалити останнє відео з YouTube |
| 📁 Отримати файли | відкрити підменю генерації файлів (inline) |
| 🔄 Перезавантажити | скинути FSM-стан |

Підменю «Отримати файли» (inline-кнопки, `files_keyboard()`):

| Кнопка | callback_data | Що робить |
|---|---|---|
| 🛒 Для Розетки | `files:rozetka` | відео-фід для Rozetka (інкрементально) |
| 🌐 Для сайту | `files:site` | відео-фід для сайту |
| 📊 Звіт .xlsx | `files:report` | звіт зі співставлень |
| 💰 Оновлення цін (SalesDrive) | `files:prices` | **[нове]** ціни/залишки з YML → xlsx |
| 🎨 Конвертація файлу цін | `files:convert` | **[нове]** лишити тільки виділені рядки |
| 📝 Оновлення описів | `files:descr` | **[нове]** звести розміри по групі в опис |
| ← Назад | `files:back` | закрити підменю |

---

## 2. Архітектура

```
Telegram  ──►  polling.py (aiogram Dispatcher)  ──►  app/telegram/router.py
                                                          │
                                                          ▼  .delay()
                                                   Celery (Redis broker)
                                                          │
                          ┌───────────────┬───────────────┼───────────────┐
                          ▼               ▼               ▼               ▼
                 video_pipeline    photo_pipeline    files_task      undo_task
                          │               │               │
                          ▼               ▼               ▼
                   YouTube/overlay   JPG-стиск     YML→xlsx генератори
                          │               │
                          ▼               ▼
                   Telegram-група   Telegram-група
```

- **Точки входу:**
  - [polling.py](../polling.py) — основний прод-режим (long polling).
  - [main.py](../main.py) — FastAPI + webhook (резервний режим, у проді не використовується).
  - [start.py](../start.py) — допоміжний локальний запуск.
- **Telegram-шар:** `app/telegram/` (`router.py`, `keyboard.py`, `states.py`).
- **Фонові задачі:** `app/tasks/` (Celery).
- **Сервіси (бізнес-логіка):** `app/services/`.
- **Доступ до даних:** `app/database/` (Supabase, або SQLite-мок при `USE_MOCKS=true`).

---

## 3. Що зроблено в останній серії робіт (червень 2026)

Усе нижче — нові фічі поверх базового бота. Кожна — окрема кнопка в «Отримати файли».

### 3.1. 💰 Оновлення цін (SalesDrive) — `files:prices`
- Файл: [app/services/salesdrive_prices.py](../app/services/salesdrive_prices.py),
  задача `run_generate_prices_file` у [app/tasks/files_task.py](../app/tasks/files_task.py).
- Качає YML-фід SalesDrive, парсить кожен `<offer>` і будує xlsx з колонками:
  **ID товару/послуги · Товар/Послуга · SKU · Ціна · Знижка · Ціна зі знижкою · Залишок на складі**.
- Маппінг з фіду (важливо): у YML `<price>` — це **фінальна** ціна, `<oldprice>` —
  оригінальна. Тому: `Ціна = oldprice` (база), `Знижка = oldprice − price`,
  `Ціна зі знижкою = price`. Якщо `oldprice` немає → знижка порожня.
- `ID товару/послуги` та `SKU` = `<article>`. `Товар/Послуга` = `<name>` (RU, бо
  це основна назва). Рядки **відсортовані за SKU** (щоб однакові моделі стояли поруч).

### 3.2. 🎨 Конвертація файлу цін — `files:convert`
- Файл: [app/services/price_file_converter.py](../app/services/price_file_converter.py),
  хендлер `handle_price_file` + стан `PriceFileConvert.waiting_file`.
- Користувач вручну редагує будь-який xlsx (хоч повний шаблон SalesDrive з усіма
  колонками, цінами на маркетплейси тощо), **виділяє кольором** змінені рядки і
  надсилає файл боту. Бот повертає файл, де **лишилися тільки виділені рядки**
  (заголовок зберігається завжди).
- Визначення «виділено»: перевіряється заливка комірки (`PatternFill`/`GradientFill`,
  `fgColor`/`bgColor`) **і** колір тексту (`font.color`). Ігноруються дефолтні
  (білий/чорний/прозорий, indexed 64 = auto, theme 0/1).

### 3.3. 📝 Оновлення описів — `files:descr`
- Файл: [app/services/description_updater.py](../app/services/description_updater.py),
  задача `run_generate_descriptions_file`.
- **Призначення:** у фіді кожна картка-варіант містить таблицю замірів **тільки
  свого діапазону розмірів** (напр. `XS-S, M-L` в одних картках, `L-XL, 2XL-3XL` в
  інших того ж товару). Фіча **зводить усі заміри групи разом** і дописує **повну**
  таблицю в опис кожної картки — і UA, і RU.
- Логіка:
  1. Групує `<offer>` по моделі (база SKU до першого `_`, напр. `26.2623`).
  2. Парсить блок замірів з опису: заголовок `Заміри/Замеры/Розміри/Размеры`, далі
     рядки `- Назва: SIZE (значення), …`.
  3. **Зливає** таблиці всіх варіантів групи (об'єднання розмірів і міток).
  4. **Виправляє опечатки міток** у межах групи (fuzzy-match ≥ 0.90; канонічне
     написання — за глобальною частотою у всьому фіді). Напр. `Обхват фгрудей` →
     `Обхват грудей`.
  5. **Крос-заповнення мов:** якщо в товара є таблиця тільки UA (а RU без замірів) —
     RU будується перекладом міток (UA↔RU словник вивчається з товарів, де є обидві
     мови). Значення цифр однакові, перекладаються лише назви.
  6. **Заміна на місці:** старий блок замірів замінюється тільки в межах секції (від
     слова-заголовка до останнього значення), увесь інший HTML (вступ, закриваючі
     теги) лишається недоторканим.
- **Вихід:** xlsx `update_rs_descr_<ДД.ММ.РРРР>.xlsx`, колонки
  **ID товару/послуги · SKU · Опис · Опис (UA)**. У файл потрапляють **тільки
  рядки, що реально змінюються** (ідемпотентно — повторний прогін після імпорту
  дає менше/0 рядків).

> **Чому модель «зникає» з файлу після імпорту:** це нормально. Якщо описи вже
> оновлені у CRM — нова генерація не бачить змін і пропускає групу. Якщо додати
> новий розмір у групу — об'єднана таблиця росте і **вся група** знову потрапляє у
> файл.

### 3.4. Особливості реального YML-фіду Aksan (висновки з аналізу 2794 офферів)
- Публічний фід: `https://aksan.salesdrive.me/export/yml/export.yml?publicKey=…`
  (ключ зберігати в `.env` як `SALESDRIVE_YML_URL`, **не комітити**).
- Теги офера: `<name>` (RU), `<name_ua>`, `<price>`, `<oldprice>` (≈70% офферів),
  `<quantity_in_stock>`, `<categoryId>`, `<vendor>`, `<article>`/`<vendorCode>`,
  `<description>` (RU, HTML), `<description_ua>`, кілька `<picture>`, багато `<param>`.
- SKU-формат: `МОДЕЛЬ_колір_розмір`, напр. `26.2873_red_40(S)` або діапазон
  `26.2623_black_46(L)-48(XL)`. Розмір у дужках — канонічний (S/M/L/XL/2XL…).
- Заголовок замірів буває **4 варіанти**: `Заміри`, `Замеры`, `Розміри`, `Размеры`.
- У джерелі трапляються опечатки міток і розбіжності RU↔UA значень (брак вхідних
  даних, не баг скрипта).

---

## 4. Змінні оточення (`.env`)

Створити `.env` з [.env.example](../.env.example). Повний перелік ключів і
призначення:

| Ключ | Призначення |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота від @BotFather |
| `TELEGRAM_TARGET_CHAT_ID` | ID групи/каналу для готової медіа (напр. `-100…`) |
| `TELEGRAM_WEBHOOK_URL` | лише для webhook-режиму (у проді не треба) |
| `TELEGRAM_WEBHOOK_SECRET` | секрет webhook (лише для webhook-режиму) |
| `TELEGRAM_ALLOWED_USERS` | дозволені user_id через кому; порожньо = усі |
| `DEPLOY_NOTIFY_CHAT_ID` | куди слати «Я оновився. Commit: …» |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | MTProto (Telethon) для файлів >20 МБ |
| `YOUTUBE_CHANNEL_ID` | канал для завантаження відео |
| `YOUTUBE_CLIENT_SECRETS_FILE` | шлях до OAuth JSON (Google Cloud) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | БД (service role key) |
| `SUPABASE_STORAGE_BUCKET` | бакет для оброблених відео (public) |
| `REDIS_URL` | брокер Celery, напр. `redis://localhost:6379/0` |
| `SALESDRIVE_YML_URL` | **публічний YML-фід** (потрібен для цін/описів) |
| `ROZETKA_API_KEY` | ключ продавця Rozetka |
| `USE_MOCKS` | `true` = усі зовнішні сервіси імітуються; `false` = реальні |
| `TEMP_VIDEO_DIR` | тимчасова тека (за замовч. `tmp/videos`) |
| `LOG_LEVEL` | `INFO`/`DEBUG`/… |

> Для тесту **тільки генераторів цін/описів** достатньо `SALESDRIVE_YML_URL` +
> `USE_MOCKS=false`. Telegram/YouTube/Supabase для цього не потрібні.

---

## 5. Запуск ЛОКАЛЬНО

### Варіант A — нативно (Windows, PowerShell) — як у проді

```powershell
# 0. бути в корені проєкту
cd D:\Aksan_tel_bot

# 1. віртуальне середовище
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install telethon cryptg   # для великих файлів

# 2. .env
Copy-Item .env.example .env
notepad .env        # заповнити токени; для дев можна лишити USE_MOCKS=true

# 3. Redis (потрібен для Celery). На Windows — Memurai або Docker:
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 4. ДВА процеси у двох окремих терміналах:
# 4a. бот (polling)
.\venv\Scripts\python.exe polling.py
# 4b. Celery worker (на Windows — solo pool!)
.\venv\Scripts\celery.exe -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

### Варіант B — Docker Compose (усе одразу: redis + web + worker + flower)

```powershell
cd D:\Aksan_tel_bot
Copy-Item .env.example .env   # заповнити
docker compose up -d --build
# health: http://localhost:8000/health   |   Flower (моніторинг черги): http://localhost:5555
docker compose logs -f --tail=100        # логи
docker compose down                       # стоп
```

> Готові .bat-обгортки в корені: `start.bat`, `stop.bat`, `restart.bat`,
> `update.bat`, `logs.bat`. **Увага:** `start.bat` має зашитий чужий шлях
> `H:\AKSAN\…` і ngrok-домен — для цього клону краще використовувати команди вище.

### Корисне (Makefile, через `make` або вручну)

```bash
make run      # uvicorn main:app --reload   (webhook-режим, дев)
make worker   # celery worker --concurrency=2
make flower   # celery flower --port=5555
make test     # pytest tests/ -v
make lint     # py_compile усіх файлів
```

---

## 6. Тести

```powershell
# увесь набір
.\venv\Scripts\python.exe -m pytest tests\ -v --tb=short

# точкові (швидко, перед пушем)
.\venv\Scripts\python.exe -m pytest tests\test_webhook.py
.\venv\Scripts\python.exe -m pytest tests\test_pipeline.py tests\test_sku_parser.py tests\test_files_generator.py
```

> Для нових сервісів цін/описів окремих pytest-тестів поки немає (див. TODO §9).
> Перевірялись офлайн-скриптами проти живого фіду.

---

## 7. ДЕПЛОЙ на сервер (детально)

### 7.1. Модель деплою

**Push-based, без ручного SSH.** Сервер — Windows із встановленим **self-hosted
GitHub Actions runner**. Будь-який `git push` у `main`:

1. GitHub запускає workflow **Deploy Bot** — [.github/workflows/deploy.yml](../.github/workflows/deploy.yml).
2. Self-hosted runner на сервері виконує його, заходить у
   `C:\bots\telegram_aksan_bot` (або `$env:DEPLOY_PROJECT_ROOT`) і запускає `.\deploy.ps1`.
3. [deploy.ps1](../deploy.ps1) робить:
   - `git config --system --add safe.directory <root>`
   - `git remote set-url origin https://github.com/MaxSaiets/Aksan_telegram_bot.git`
   - `git fetch origin` → `git reset --hard origin/main` (жорстке вирівнювання під remote)
   - `pip install --upgrade pip` + `pip install -r requirements.txt` + `telethon cryptg`
   - `Restart-Service aksan_bot_polling`
   - `Restart-Service aksan_bot_worker`
   - `python -m app.services.deploy_notify <short_sha>` → шле в Telegram «Я оновився…»

### 7.2. Звичайний робочий цикл (як деплоїти зміну)

```powershell
cd D:\Aksan_tel_bot
# (зробити правки)
.\venv\Scripts\python.exe -m pytest tests\test_webhook.py   # швидка перевірка
git add .
git commit -m "Короткий зрозумілий опис"
git push origin main
# → відкрити GitHub → вкладка Actions → workflow "Deploy Bot" має стати зеленим
# → у Telegram прийде "Я оновився. Commit: <sha>"
```

Подивитись статус деплою з консолі (якщо є `gh`):

```powershell
gh run list --workflow "Deploy Bot" --limit 5
gh run watch                       # стежити за поточним
```

### 7.3. Що має бути на сервері (одноразове налаштування)

- Windows + **Python 3.11**, **FFmpeg** у `PATH`, **Memurai/Redis** як служба.
- Каталог проєкту `C:\bots\telegram_aksan_bot` (може бути junction на реальну теку).
- `venv` зібраний **на самому сервері** (копіювати venv з іншої машини — ламається).
- `.env` лежить у корені проєкту на сервері (його немає в git).
- Дві Windows-служби (через NSSM):
  - `aksan_bot_polling` → запускає `venv\Scripts\python.exe polling.py`
  - `aksan_bot_worker` → запускає `celery -A app.tasks.celery_app worker --pool=solo`
- Запущений **self-hosted GitHub runner** як служба під акаунтом з правами на теку.

### 7.4. Ручні команди на сервері (через RDP/локально)

> Прямого SSH немає; на сервер заходять по **RDP** (креди не в репозиторії —
> питати власника). Усі команди — PowerShell у корені проєкту.

```powershell
cd C:\bots\telegram_aksan_bot

git rev-parse --short HEAD                 # який коміт зараз задеплоєний
Get-Service aksan_bot_polling, aksan_bot_worker   # статус служб

.\deploy.ps1                               # ручний деплой (те саме, що CI)

Restart-Service aksan_bot_polling          # рестарт окремо
Restart-Service aksan_bot_worker

# перевірити сповіщення про деплой
.\venv\Scripts\python.exe -m app.services.deploy_notify test123
# очікувано в Telegram: "Я оновився. Commit: test123"
```

### 7.5. Реєстрація webhook (лише якщо колись знадобиться webhook-режим)

```powershell
# Docker:
docker compose exec web python scripts/register_webhook.py
# або нативно:
.\venv\Scripts\python.exe scripts\register_webhook.py
```

---

## 8. Діагностика «бот не відповідає»

Перевіряти строго по порядку:

1. **GitHub Actions** → останній «Deploy Bot» зелений?
2. На сервері: `git rev-parse --short HEAD` — збігається з останнім комітом?
3. `Get-Service aksan_bot_polling, aksan_bot_worker` — обидві `Running`?
4. `.env` валідний (токен, `USE_MOCKS=false`, `REDIS_URL`)?
5. Запустити вручну `.\venv\Scripts\python.exe polling.py` — бачити помилку.
6. Запустити вручну worker — `… celery … worker --pool=solo`.
7. Логи в теці `tmp\`.

**Типові поломки, що вже були:** зламаний `venv` після копіювання з іншої машини
(рішення — перезібрати venv на сервері); права runner-служби; `git safe.directory`
на Windows (уже у скрипті); кирилиця у шляхах (тому канонічний шлях
`C:\bots\telegram_aksan_bot`); `getaddrinfo failed` = Supabase недоступний/проєкт
на паузі (Resume у дашборді Supabase).

---

## 9. Що ще можна / треба зробити (TODO)

- [ ] **Pytest-тести** для нових сервісів: `salesdrive_prices`, `price_file_converter`,
      `description_updater` (зараз покриті лише ручними офлайн-перевірками).
- [ ] У `files:descr` за бажанням — режим «усі товари з замірами» (а не лише змінені)
      для повторного імпорту/звірки. Обговорювалось, не реалізовано.
- [ ] Опційний **звіт про розбіжності RU≠UA** у фіді (15 товарів типу `26.2939`,
      де в джерелі різні значення) — окремий аркуш для ручного фіксу в CRM.
- [ ] `start.bat` містить зашитий чужий шлях `H:\AKSAN\…` і ngrok-домен — за потреби
      привести до поточного оточення.
- [ ] `config.py` має mojibake в коментарях (не критично; за дотику — переписати в UTF-8).
- [ ] Розглянути прибирання залишкового `ngrok` / webhook-шляху, якщо webhook не
      планується (за AGENTS.md polling — канон).

---

## 10. Важливі правила проєкту (не порушувати без причини)

З [AGENTS.md](../AGENTS.md):

- Прод-режим — **polling**, не webhook+ngrok.
- Не редагувати файли на сервері напряму, поки CI/CD живий — правити локально й пушити.
- **Тільки точне співставлення** моделей/категорій; не повертати fuzzy-matching.
- Усі тексти для користувача — чистий **UTF-8** (були проблеми з mojibake).
- Для фото — **append-only** історія батчів, не перезаписувати попередні.
- Для відео — завантаження не залежить від пошуку в каталозі; уся логіка
  співставлення/експорту живе у генерації файлів.
- Розміри: `норма` = 40/42/44 (+46 якщо є 42/44 і немає 40); `ботал` = 50/52/54;
  `супер ботал` = 56/58/60.

---

## 11. Карта ключових файлів

| Файл | Призначення |
|---|---|
| [polling.py](../polling.py) | прод-запуск бота (long polling) |
| [main.py](../main.py) | FastAPI + webhook (резерв) |
| [config.py](../config.py) | усі налаштування (pydantic Settings) |
| [app/telegram/router.py](../app/telegram/router.py) | усі хендлери, стани, кнопки |
| [app/telegram/keyboard.py](../app/telegram/keyboard.py) | клавіатури та callback-константи |
| [app/telegram/states.py](../app/telegram/states.py) | FSM-стани |
| [app/tasks/files_task.py](../app/tasks/files_task.py) | Celery-задачі генерації файлів |
| [app/services/salesdrive_prices.py](../app/services/salesdrive_prices.py) | **ціни/залишки → xlsx** |
| [app/services/price_file_converter.py](../app/services/price_file_converter.py) | **фільтр виділених рядків** |
| [app/services/description_updater.py](../app/services/description_updater.py) | **зведення розмірів в описи** |
| [app/services/files_generator.py](../app/services/files_generator.py) | Rozetka/site відео-фіди |
| [app/services/salesdrive.py](../app/services/salesdrive.py) | парсинг YML-каталогу |
| [app/services/sku_parser.py](../app/services/sku_parser.py) | модель/категорія/розміри |
| [app/services/deploy_notify.py](../app/services/deploy_notify.py) | сповіщення про деплой |
| [deploy.ps1](../deploy.ps1) | серверний деплой-скрипт |
| [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) | CI/CD workflow |
| [docker-compose.yml](../docker-compose.yml) | redis + web + worker + flower |

Решта довідки: [README.md](../README.md), [docs/PROJECT_CONTEXT.md](PROJECT_CONTEXT.md),
[docs/CI_CD.md](CI_CD.md), [docs/LLM_HANDOFF.md](LLM_HANDOFF.md),
[docs/OPS_BOOTSTRAP.md](OPS_BOOTSTRAP.md).
```
