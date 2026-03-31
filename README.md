# 🤖 Telegram-бот: Фінанси для підлітків

Автоматичний освітній Telegram-канал для учнів 7–11 класу.
**Stack:** Python · Gemini API · Pexels API · Render.com

---

## 📁 Структура проєкту

```
finance_bot/
├── bot.py               # Головний файл, scheduler, keep-alive
├── content_generator.py # Генерація постів через Gemini
├── media_fetcher.py     # Фото з Pexels API
├── schedule_config.py   # Розклад тижня і теми
├── requirements.txt
├── render.yaml          # Конфіг для Render.com
└── .env.example         # Шаблон змінних середовища
```

---

## 🗓 Розклад публікацій

| День | Тема | Формат |
|------|------|--------|
| Пн | 🌍 Економіка | Пояснення концепції |
| Вт | 🤖 ШІ та технології | Пояснення + практика |
| Ср | 📈 Фондовий ринок | Розбір компанії/концепції |
| Чт | ₿ Крипто | Пояснення + безпека |
| Пт | 💰 Фінансові лайфхаки | Практичний хак |
| Сб | 🎮 Інтерактив | Опитування (без фото) |
| Нд | 🧾 Дайджест | Огляд тижня |

---

## 🚀 Деплой на Render.com

### 1. Підготовка

**Отримай API ключі:**
- [Telegram Bot Token](https://t.me/BotFather) → `/newbot`
- [Gemini API Key](https://aistudio.google.com/app/apikey) → безкоштовно
- [Pexels API Key](https://www.pexels.com/api/) → безкоштовно, без картки

**Підготуй канал:**
1. Створи Telegram-канал
2. Додай бота як адміністратора з правом публікації
3. Скопіюй username каналу (@mychannel) або ID (-100xxxxxxxxxx)

### 2. Завантаж на GitHub

```bash
git init
git add .
git commit -m "Initial bot setup"
git remote add origin https://github.com/yourusername/finance-bot.git
git push -u origin main
```

### 3. Render.com

1. Зайди на [render.com](https://render.com) → **New Web Service**
2. Підключи GitHub репозиторій
3. Налаштування:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
4. Додай **Environment Variables** (вкладка Environment):

```
TELEGRAM_BOT_TOKEN     = токен від BotFather
TELEGRAM_CHANNEL_ID    = @назваканалу
ADMIN_TELEGRAM_ID      = твій Telegram ID (отримай у @userinfobot)
GEMINI_API_KEY         = ключ з Google AI Studio
PEXELS_API_KEY         = ключ з Pexels
RENDER_URL             = https://назва-твого-сервісу.onrender.com
BOT_TIMEZONE           = Europe/Kyiv
POST_HOUR              = 10
POST_MINUTE            = 0
PORT                   = 8080
```

5. Натисни **Deploy** ✅

---

## ⚙️ Команди адміна (в особистому чаті з ботом)

| Команда | Дія |
|---------|-----|
| `/start` | Статус та довідка |
| `/post` | Згенерувати і опублікувати пост зараз |
| `/status` | Поточна тема, час наступної публікації |
| `/test` | Перевірити підключення до Gemini, Pexels, Telegram |

---

## 🔧 Keep-alive (Render free tier)

Бот сам пінгує себе кожні **5 хвилин** через `/health` endpoint.
Render не засипає поки є HTTP-активність.

> ⚠️ **Free tier Render:** іноді все одно засипає після 15 хв без зовнішніх запитів.  
> Рішення: додай безкоштовний **UptimeRobot** → пінгуй `https://твій-сервіс.onrender.com/health` кожні 5 хв.

---

## 🛠 Локальний запуск

```bash
# Встановити залежності
pip install -r requirements.txt

# Скопіювати та заповнити .env
cp .env.example .env
# відредагуй .env своїми ключами

# Запустити
python bot.py
```

---

## 📦 Міграція на Hetzner (коли будеш готовий)

```bash
# На сервері
sudo apt update && sudo apt install python3-pip python3-venv -y

git clone https://github.com/yourusername/finance-bot.git
cd finance-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Встанови змінні у .env
cp .env.example .env && nano .env

# Запуск через systemd (автозапуск після перезавантаження)
sudo nano /etc/systemd/system/financebot.service
```

**financebot.service:**
```ini
[Unit]
Description=Finance Teen Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/finance-bot
EnvironmentFile=/home/ubuntu/finance-bot/.env
ExecStart=/home/ubuntu/finance-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable financebot
sudo systemctl start financebot
sudo systemctl status financebot
```
