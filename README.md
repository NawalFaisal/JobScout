# 🚀 JobScout - Automated Canadian Internship Finder

## 📋 The Problem
Manually checking 13+ company career sites daily for internships is:
- **Time-consuming** (1-2 hours daily)
- **Easy to miss** new postings  
- **Repetitive and frustrating**

## ✅ The Solution
JobScout automatically:
1. **Scrapes** 13 major Canadian company career sites every 30 minutes
2. **Filters** for tech internships, co-ops, and student positions only
3. **Saves** new jobs to PostgreSQL database (no duplicates)
4. **Alerts** you via Telegram the moment new jobs are posted
5. **Exports** to Excel with color-coded priority levels

**Result:** Reduce job search time by 90%, never miss a new posting.

## 🏢 Companies Monitored
| Banks | Telecom | Tech | Consulting |
|-------|---------|------|------------|
| RBC | Rogers | Amazon | Deloitte |
| TD | Telus | Microsoft | |
| CIBC | Bell | Shopify | |
| Scotiabank | | | |
| BMO | | | |
| Manulife | | | |

## 🛠️ Tech Stack
- **Backend:** Python, FastAPI, SQLAlchemy
- **Scraping:** Playwright (browser automation)
- **Database:** PostgreSQL
- **Notifications:** Telegram Bot API
- **Scheduling:** APScheduler
- **Containerization:** Docker & Docker Compose
- **Export:** Pandas, OpenPyXL (Excel generation)

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Telegram Bot Token (optional, for notifications)

### 1. Clone the repository
```bash
git clone https://github.com/NawalFaisal/JobScout.git
cd JobScout

2. Configure environment
bash
cp .env.example .env
# Edit .env with your settings
3. Start with Docker
bash
docker compose up --build -d
4. Verify it's running
bash
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
📡 API Endpoints
Method	Endpoint	Description
GET	/	API info and monitored companies
GET	/health	Health check
GET	/jobs	List all saved jobs
GET	/stats	Scraping statistics
POST	/scrape	Trigger manual scrape
GET	/export/excel	Download jobs as Excel file
GET	/test-scrape	Run synchronous test scrape
🔔 Telegram Notifications
Get instant alerts when new jobs are found:

text
🚨 NEW BMO INTERNSHIP!

💼 Software Developer Intern - Summer 2026
📍 Toronto, ON  
⏰ Posted 15 minutes ago

🔗 https://bmo.wd3.myworkdayjobs.com/...

APPLY NOW! 🚀
Setup Telegram Notifications
Create a bot with @BotFather

Get your Chat ID by messaging @userinfobot

Add to .env:

env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
📁 Project Structure
text
JobScout/
├── backend/
│   ├── main.py              # FastAPI app + scrapers
│   ├── Dockerfile
│   └── requirements.txt
├── telegram-bot/
│   ├── bot.py
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
└── README.md
⚙️ Configuration
Environment Variables
Variable	Description	Required
DATABASE_URL	PostgreSQL connection string	Yes
TELEGRAM_BOT_TOKEN	Telegram bot token	No
TELEGRAM_CHAT_ID	Your Telegram chat ID	No
Customizing Job Filters
Edit TECH_KEYWORDS and EXCLUDE_KEYWORDS in main.py:

python
TECH_KEYWORDS = [
    'software', 'developer', 'data', 'engineer', 
    'python', 'java', 'react', 'cloud', ...
]

EXCLUDE_KEYWORDS = [
    'mechanical', 'civil', 'sales', 'marketing', ...
]
📊 Excel Export
Export jobs with color-coded priority:

Priority	Color	Age
🚨 URGENT	Red	< 1 hour
⚠️ FRESH	Yellow	< 3 hours
🟡 RECENT	Light	< 12 hours
🔵 OLD	Default	> 12 hours
bash
curl http://localhost:8000/export/excel --output jobs.xlsx
🧪 Development
Run locally (without Docker)
bash
cd backend
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
View logs
bash
docker compose logs -f backend
Test Playwright
bash
docker exec -it jobscout-backend bash
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright works')"
🤝 Contributing
Fork the repository

Create a feature branch (git checkout -b feature/new-company)

Commit changes (git commit -m 'Add new company scraper')

Push to branch (git push origin feature/new-company)

Open a Pull Request

📝 License
MIT License - feel free to use this project for your own job search!

👤 Author
Nawal Faisal
GitHub: @NawalFaisal

LinkedIn: nawalfaisal