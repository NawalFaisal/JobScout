from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
import pandas as pd
import os
import time
import re
import traceback
import sys
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# Forced output for Docker logs
sys.stdout.reconfigure(line_buffering=True)
print("🚀 JobScout Backend Starting...", flush=True)

# ===== CONFIG =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Tech keywords
TECH_KEYWORDS = [
    'software', 'developer', 'programming', 'engineer', 'web', 'backend', 'frontend',
    'data', 'analytics', 'database', 'sql', 'python', 'java', 'javascript', 'typescript',
    'cloud', 'devops', 'aws', 'azure', 'ci/cd', 'kubernetes', 'docker',
    'security', 'cybersecurity', 'infosec',
    'qa', 'test', 'quality assurance', 'automation', 'sdet',
    'machine learning', 'ml', 'ai',
    'full stack', 'fullstack', 'api', 'react', 'node', 'mobile',
    'sre', 'site reliability', 'infrastructure', '.net', 'c++', 'c#','business analyst',
]

EXCLUDE_KEYWORDS = [
    'mechanical', 'civil', 'electrical', 'chemical', 'industrial',
    'construction', 'mining', 'drilling', 'geology',
    'structural', 'automotive', 'manufacturing',
    'sales', 'marketing', 'finance', 'accounting', 'hr',
    'project manager', 'product manager',
    'technician', 'field service'
]

# Workday Companies
WORKDAY_COMPANIES = {
    'RBC': 'https://jobs.rbc.com/ca/en/students',
    'TD': 'https://jobs.td.com/en-CA/campus-and-entry-level/',
    'CIBC': 'https://cibc.wd3.myworkdayjobs.com/campus',
    'Scotiabank': 'https://jobs.scotiabank.com/search/?createNewAlert=false&q=intern&locationsearch=canada',
    'Rogers': 'https://rogers.wd3.myworkdayjobs.com/Rogers_Campus_Careers',
    'Telus': 'https://telus.taleo.net/careersection/10000/jobsearch.ftl?keyword=intern',
    'Bell': 'https://jobs.bce.ca/ca/en/student',
    'BMO': 'https://bmo.wd3.myworkdayjobs.com/Campus',
    'Manulife': 'https://manulife.wd3.myworkdayjobs.com/MFCJH_Students',
    'Deloitte': 'https://apply.deloitte.com/careers/SearchJobs/intern%20canada',
    'Amazon': 'https://www.amazon.jobs/en/search?offset=0&result_limit=10&sort=recent&country=CAN&category=student-programs',
    'Microsoft': 'https://careers.microsoft.com/students/us/en/search-results?keywords=intern',
    'Shopify': 'https://www.shopify.com/careers/search?specialties%5B%5D=interns&keywords=&sort=specialty_asc',
}

# ===== DATABASE =====
engine = None
SessionLocal = None
Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    company = Column(String(100))
    url = Column(String(500), unique=True)
    location = Column(String(100))
    description = Column(Text, nullable=True)
    found_date = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50))
    is_internship = Column(Boolean, default=True)
    posted_date = Column(DateTime, nullable=True)
    notified = Column(Boolean, default=False)

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer)
    status = Column(String(50), default="NEW")
    applied_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_database():
    global engine, SessionLocal
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres:5432/jobscout")
    
    for i in range(10):
        try:
            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Connected to PostgreSQL")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            return
        except Exception as e:
            if i < 9:
                print(f"⚠️ Retrying PostgreSQL... ({i+1}/10)")
                time.sleep(3)
            else:
                raise

# ===== FILTERING =====
def is_tech_role(title, description=""):
    """Check if actually tech"""
    text = (title + " " + description).lower()
    
    for keyword in EXCLUDE_KEYWORDS:
        if keyword.lower() in text:
            return False
    
    for keyword in TECH_KEYWORDS:
        if keyword.lower() in text:
            return True
    
    return False

def parse_workday_date(date_text):
    """Parse Workday date formats"""
    if not date_text:
        return datetime.utcnow()
    
    date_text = date_text.lower().strip()
    now = datetime.utcnow()
    
    # "Posted 2 days ago"
    if 'day' in date_text:
        match = re.search(r'(\d+)\s*day', date_text)
        if match:
            return now - timedelta(days=int(match.group(1)))
    
    if 'hour' in date_text:
        match = re.search(r'(\d+)\s*hour', date_text)
        if match:
            return now - timedelta(hours=int(match.group(1)))
    
    if 'today' in date_text or 'just posted' in date_text:
        return now - timedelta(hours=2)
    
    return now

# ===== TELEGRAM =====
def send_telegram_notification(job):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    try:
        age_mins = int((datetime.utcnow() - job['posted_date']).total_seconds() / 60)
        
        message = f"""🚨 NEW {job['company'].upper()} INTERNSHIP!

💼 {job['title']}
📍 {job['location']}
⏰ Posted {age_mins} minutes ago

🔗 {job['url']}

APPLY NOW! 🚀"""
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        }, timeout=10)
        return response.status_code == 200
    except:
        return False
    

# ===== WORKDAY SCRAPER - THE REAL DEAL =====
def scrape_workday_with_playwright():
    """Scrape Workday career sites with Playwright"""
    print("\n" + "="*60, flush=True)
    print("🔍 SCRAPING WORKDAY SITES (THE GOOD STUFF)", flush=True)
    print(f"⏰ Started at: {datetime.utcnow()}", flush=True)
    print("="*60, flush=True)

    all_jobs = []

    try:
        print("🌐 Launching Playwright browser...", flush=True)
        p = sync_playwright().start()
        print("✅ Playwright context created", flush=True)

        # CRITICAL: Docker-compatible browser launch arguments
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process'
            ]
        )
        print(f"✅ Browser launched successfully", flush=True)

        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        print("✅ Browser context created", flush=True)
        
        for idx, (company, url) in enumerate(WORKDAY_COMPANIES.items(), 1):
            print(f"\n🏢 [{idx}/{len(WORKDAY_COMPANIES)}] {company}...", flush=True)
            print(f"   URL: {url[:60]}...", flush=True)

            try:
                page = context.new_page()
                print(f"   📄 Navigating to page...", flush=True)
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                print(f"   ✅ Page loaded", flush=True)

                time.sleep(3)  # Load for JS

                # WORKDAY SPECIFIC SELECTORS
                if 'myworkdayjobs.com' in url:
                    jobs = scrape_workday_myworkday(page, company)
                elif 'jobs.rbc.com' in url:
                    jobs = scrape_rbc(page, company)
                elif 'jobs.td.com' in url:
                    jobs = scrape_td(page, company)
                elif 'taleo.net' in url:
                    jobs = scrape_taleo(page, company)
                elif 'jobs.bce.ca' in url:
                    jobs = scrape_bell(page, company)
                elif 'amazon.jobs' in url:
                    jobs = scrape_amazon(page, company)
                elif 'careers.microsoft.com' in url:
                    jobs = scrape_microsoft(page, company)
                elif 'shopify.com/careers' in url:
                    jobs = scrape_shopify(page, company)
                elif 'jobs.scotiabank.com' in url:
                    jobs = scrape_generic_jobs(page, company)
                elif 'apply.deloitte.com' in url:
                    jobs = scrape_generic_jobs(page, company)
                else:
                    print(f"   ⚠️ No specific scraper for this site, using generic", flush=True)
                    jobs = scrape_generic_jobs(page, company)

                all_jobs.extend(jobs)
                print(f"   ✅ Found {len(jobs)} tech internship jobs", flush=True)

                page.close()
                time.sleep(2)  

            except PlaywrightTimeout as e:
                print(f"   ⏰ Timeout: {e}", flush=True)
                continue
            except Exception as e:
                print(f"   ❌ Error: {e}", flush=True)
                traceback.print_exc()
                continue
        
        browser.close()
        p.stop()
        print("✅ Browser closed", flush=True)

    except Exception as e:
        print(f"\n❌ PLAYWRIGHT ERROR: {e}", flush=True)
        print(f"📋 Full traceback:", flush=True)
        traceback.print_exc()
        return []

    print(f"\n{'='*60}", flush=True)
    print(f"✅ TOTAL: {len(all_jobs)} jobs from Workday sites", flush=True)
    print("="*60, flush=True)

    return all_jobs

def scrape_workday_myworkday(page, company):
    """Scrape standard Workday myworkdayjobs.com sites"""
    jobs = []
    
    try:
        page.wait_for_selector('li.css-1q2dra3', timeout=10000)
        
        job_cards = page.query_selector_all('li.css-1q2dra3')
        
        for card in job_cards[:20]:  # First 20
            try:
                # Title
                title_elem = card.query_selector('a')
                title = title_elem.inner_text().strip() if title_elem else ""
                
                # URL
                job_url = title_elem.get_attribute('href') if title_elem else ""
                if job_url and not job_url.startswith('http'):
                    base_url = page.url.split('/')[0] + '//' + page.url.split('/')[2]
                    job_url = base_url + job_url
                
                # Location
                location_elem = card.query_selector('dd.css-129m7dg')
                location = location_elem.inner_text().strip() if location_elem else "Canada"
                
                # Posted date
                date_elem = card.query_selector('dd.css-1v5hboj')
                date_text = date_elem.inner_text().strip() if date_elem else ""
                posted_date = parse_workday_date(date_text)
                
                # Must be intern/co-op
                if not any(word in title.lower() for word in ['intern', 'co-op', 'coop', 'student']):
                    continue
                
                # Must be tech
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': location[:100],
                        'description': f'Workday - {date_text}',
                        'source': 'workday',
                        'posted_date': posted_date
                    })
                    
            except Exception as e:
                continue
        
    except Exception as e:
        print(f"    Workday parse error: {e}")
    
    return jobs

def scrape_rbc(page, company):
    """RBC specific scraper"""
    jobs = []
    
    try:
        page.wait_for_selector('.search-results-list', timeout=10000)
        
        job_links = page.query_selector_all('a.job-title-link')
        
        for link in job_links[:20]:
            try:
                title = link.inner_text().strip()
                job_url = link.get_attribute('href')
                
                if job_url and not job_url.startswith('http'):
                    job_url = 'https://jobs.rbc.com' + job_url
                
                if not any(word in title.lower() for word in ['intern', 'co-op', 'student']):
                    continue
                
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'RBC Career Site',
                        'source': 'workday',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })
                    
            except:
                continue
                
    except Exception as e:
        print(f"    RBC error: {e}")
    
    return jobs

def scrape_td(page, company):
    """TD specific scraper"""
    jobs = []
    
    try:
        page.wait_for_selector('.job-card', timeout=10000)
        
        cards = page.query_selector_all('.job-card')
        
        for card in cards[:20]:
            try:
                title_elem = card.query_selector('h3 a')
                title = title_elem.inner_text().strip() if title_elem else ""
                job_url = title_elem.get_attribute('href') if title_elem else ""
                
                if job_url and not job_url.startswith('http'):
                    job_url = 'https://jobs.td.com' + job_url
                
                if not any(word in title.lower() for word in ['intern', 'co-op', 'student']):
                    continue
                
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'TD Career Site',
                        'source': 'workday',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })
                    
            except:
                continue
                
    except Exception as e:
        print(f"    TD error: {e}")
    
    return jobs

def scrape_taleo(page, company):
    """Taleo sites (Telus, etc)"""
    jobs = []
    
    try:
        page.wait_for_selector('#job', timeout=10000)
        
        rows = page.query_selector_all('tr.taleoTableRow')
        
        for row in rows[:20]:
            try:
                link = row.query_selector('a.jobTitle')
                title = link.inner_text().strip() if link else ""
                job_url = link.get_attribute('href') if link else ""
                
                if job_url and not job_url.startswith('http'):
                    base = page.url.split('/careersection')[0]
                    job_url = base + job_url
                
                if not any(word in title.lower() for word in ['intern', 'co-op', 'student']):
                    continue
                
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'Taleo Site',
                        'source': 'taleo',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })
                    
            except:
                continue
                
    except Exception as e:
        print(f"    Taleo error: {e}")
    
    return jobs

def scrape_bell(page, company):
    """Bell careers"""
    jobs = []
    
    try:
        page.wait_for_selector('.job-listing', timeout=10000)
        
        listings = page.query_selector_all('.job-listing a')
        
        for link in listings[:20]:
            try:
                title = link.inner_text().strip()
                job_url = link.get_attribute('href')
                
                if job_url and not job_url.startswith('http'):
                    job_url = 'https://jobs.bce.ca' + job_url
                
                if not any(word in title.lower() for word in ['intern', 'co-op', 'student']):
                    continue
                
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'Bell Career Site',
                        'source': 'workday',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })
                    
            except:
                continue
                
    except:
        pass
    
    return jobs

def scrape_amazon(page, company):
    """Amazon jobs"""
    jobs = []
    
    try:
        page.wait_for_selector('.job-tile', timeout=10000)
        
        tiles = page.query_selector_all('.job-tile a')
        
        for link in tiles[:20]:
            try:
                title = link.get_attribute('aria-label') or link.inner_text().strip()
                job_url = link.get_attribute('href')
                
                if job_url and not job_url.startswith('http'):
                    job_url = 'https://www.amazon.jobs' + job_url
                
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'Amazon Jobs',
                        'source': 'amazon',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })
                    
            except:
                continue
                
    except:
        pass
    
    return jobs

def scrape_microsoft(page, company):
    """Microsoft careers"""
    jobs = []
    
    try:
        page.wait_for_selector('.ms-List-cell', timeout=10000)
        
        cells = page.query_selector_all('.ms-List-cell a')
        
        for link in cells[:20]:
            try:
                title = link.inner_text().strip()
                job_url = link.get_attribute('href')
                
                if job_url and not job_url.startswith('http'):
                    job_url = 'https://careers.microsoft.com' + job_url
                
                if not is_tech_role(title):
                    continue
                
                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'Microsoft Careers',
                        'source': 'microsoft',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })
                    
            except:
                continue
                
    except:
        pass
    
    return jobs

def scrape_shopify(page, company):
    """Shopify careers"""
    jobs = []

    try:
        page.wait_for_selector('.careers-job-listing', timeout=10000)

        listings = page.query_selector_all('.careers-job-listing a')

        for link in listings[:20]:
            try:
                title = link.inner_text().strip()
                job_url = link.get_attribute('href')

                if job_url and not job_url.startswith('http'):
                    job_url = 'https://www.shopify.com' + job_url

                if not is_tech_role(title):
                    continue

                if job_url:
                    jobs.append({
                        'title': title[:150],
                        'company': company,
                        'url': job_url[:500],
                        'location': 'Canada',
                        'description': 'Shopify Careers',
                        'source': 'shopify',
                        'posted_date': datetime.utcnow() - timedelta(hours=12)
                    })

            except:
                continue

    except:
        pass

    return jobs


def scrape_generic_jobs(page, company):
    """Generic job scraper - tries common selectors"""
    jobs = []
    print(f"      🔍 Using generic scraper for {company}", flush=True)

    try:
        time.sleep(2)

        selectors_to_try = [
            'a[href*="job"]',
            'a[href*="career"]',
            'a[href*="position"]',
            '.job-title a',
            '.job-link',
            '[class*="job"] a',
            '[class*="career"] a',
            '[data-job] a',
            'li a[href*="/"]'
        ]

        all_links = []
        for selector in selectors_to_try:
            try:
                links = page.query_selector_all(selector)
                if links:
                    all_links.extend(links)
                    print(f"      📎 Found {len(links)} links with selector: {selector}", flush=True)
                    break 
            except:
                continue

        seen_urls = set()
        for link in all_links[:30]: 
            try:
                title = link.inner_text().strip()
                job_url = link.get_attribute('href')

                if not title or len(title) < 5 or len(title) > 200:
                    continue

                if job_url and not job_url.startswith('http'):
                    base_url = page.url.split('/')[0] + '//' + page.url.split('/')[2]
                    job_url = base_url + job_url

                if not job_url or job_url in seen_urls:
                    continue

                seen_urls.add(job_url)

                title_lower = title.lower()
                if not any(word in title_lower for word in ['intern', 'co-op', 'coop', 'student', 'new grad', 'entry']):
                    continue
                
                if not is_tech_role(title):
                    continue

                jobs.append({
                    'title': title[:150],
                    'company': company,
                    'url': job_url[:500],
                    'location': 'Canada',
                    'description': f'{company} Career Site',
                    'source': 'generic',
                    'posted_date': datetime.utcnow() - timedelta(hours=12)
                })

            except:
                continue

    except Exception as e:
        print(f" Generic scraper error: {e}", flush=True)

    return jobs

# ===== EXCEL =====
def generate_excel(db: Session):
    try:
        jobs = db.query(Job).order_by(Job.posted_date.desc()).limit(200).all()
        applications = {app.job_id: app for app in db.query(Application).all()}
        
        data = []
        for job in jobs:
            app = applications.get(job.id)
            age_mins = int((datetime.utcnow() - (job.posted_date or job.found_date)).total_seconds() / 60)
            
            if age_mins < 60:
                priority = "URGENT"
            elif age_mins < 180:
                priority = "FRESH"
            elif age_mins < 720:
                priority = "RECENT"
            else:
                priority = "OLD"
            
            data.append({
                'Priority': priority,
                'Company': job.company,
                'Title': job.title,
                'Location': job.location,
                'Age (mins)': age_mins,
                'Status': app.status if app else 'NEW',
                'Notes': app.notes if app else '',
                'Source': job.source,
                'URL': job.url,
                'APPLY': f'=HYPERLINK("{job.url}", "CLICK TO APPLY")'
            })
        
        df = pd.DataFrame(data)
        filepath = '/app/jobs.xlsx'
        df.to_excel(filepath, index=False)
        
        # Format
        wb = load_workbook(filepath)
        ws = wb.active
        
        # Header
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(1, col)
            cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            cell.font = Font(color="FFFFFF", bold=True)
        
        ws.column_dimensions['A'].width = 15
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 50
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 12
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 30
        ws.column_dimensions['H'].width = 15
        ws.column_dimensions['I'].width = 60
        ws.column_dimensions['J'].width = 20
        
        for row in range(2, ws.max_row + 1):
            age = ws.cell(row, 5).value
            if age and age < 60:
                fill = PatternFill(start_color="FF6B6B", end_color="FF6B6B", fill_type="solid")
                for col in range(1, ws.max_column + 1):
                    ws.cell(row, col).fill = fill
            elif age and age < 180:
                fill = PatternFill(start_color="FFE66D", end_color="FFE66D", fill_type="solid")
                for col in range(1, ws.max_column + 1):
                    ws.cell(row, col).fill = fill
        
        ws.freeze_panes = 'A2'
        wb.save(filepath)
        return filepath
    except:
        return None

# ===== FASTAPI =====
app = FastAPI(title="JobScout Workday Edition")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_database()

def get_db():
    if not SessionLocal:
        raise HTTPException(503, "DB not ready")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def root():
    return {
        "message": "JobScout - Workday Edition 🚀",
        "version": "9.0 - WORKDAY SCRAPER",
        "companies": list(WORKDAY_COMPANIES.keys())
    }

@app.post("/scrape")
def scrape(background_tasks: BackgroundTasks):
    """Trigger background scraping - creates its own DB session"""
    print("\n" + "="*60, flush=True)
    print("📨 POST /scrape - Triggering background task...", flush=True)
    print("="*60, flush=True)
    background_tasks.add_task(run_scrape)
    return {"message": "Scraping Workday sites...", "status": "started"}


def run_scrape():
    """Run scraper with its own database session - CRITICAL FIX"""
    print("\n" + "🔥"*30, flush=True)
    print("🚀 BACKGROUND SCRAPE TASK STARTED!", flush=True)
    print(f"⏰ Time: {datetime.utcnow()}", flush=True)
    print("🔥"*30 + "\n", flush=True)

    # Not passed from request creating own session
    if not SessionLocal:
        print("❌ ERROR: Database not initialized!", flush=True)
        return

    db = SessionLocal()
    print("✅ Created new database session for background task", flush=True)

    try:
        # Test DB connection
        db.execute(text("SELECT 1"))
        print("✅ Database connection verified", flush=True)

        # Run the scraper
        print("\n📞 Calling scrape_workday_with_playwright()...", flush=True)
        jobs = scrape_workday_with_playwright()
        print(f"\n✅ Scraper returned {len(jobs)} jobs", flush=True)

        new = 0
        notified = 0

        for job in jobs:
            try:
                clean_url = job['url'].split('?')[0]
                existing = db.query(Job).filter(Job.url.contains(clean_url[:100])).first()

                if existing:
                    print(f"  ⏭️ Skipping duplicate: {job['title'][:40]}", flush=True)
                    continue

                new_job = Job(
                    title=job['title'],
                    company=job['company'],
                    url=job['url'],
                    location=job['location'],
                    description=job.get('description', ''),
                    source=job['source'],
                    found_date=datetime.utcnow(),
                    posted_date=job.get('posted_date', datetime.utcnow()),
                    notified=False
                )
                db.add(new_job)
                db.flush()

                new += 1

                # Telegram
                age = int((datetime.utcnow() - job['posted_date']).total_seconds() / 60)
                if age < 360: 
                    if send_telegram_notification(job):
                        new_job.notified = True
                        notified += 1
                        print(f"  📱 Telegram sent: {job['company']}: {job['title'][:40]}", flush=True)

                print(f"  ✅ NEW: {job['company']}: {job['title'][:50]}", flush=True)

            except Exception as e:
                print(f"  ❌ Error saving job: {e}", flush=True)
                traceback.print_exc()

        db.commit()
        print(f"\n" + "="*60, flush=True)
        print(f"📊 SCRAPE COMPLETE: {new} new jobs, {notified} notifications", flush=True)
        print("="*60, flush=True)

        # Generate Excel
        generate_excel(db)
        print("📁 Excel file generated", flush=True)

    except Exception as e:
        print(f"\n❌ FATAL ERROR IN run_scrape(): {e}", flush=True)
        traceback.print_exc()
        db.rollback()

    finally:
        db.close()
        print("🔒 Database session closed", flush=True)

@app.get("/jobs")
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.posted_date.desc()).limit(100).all()
    return {"count": len(jobs), "jobs": [{"id": j.id, "title": j.title, "company": j.company, "url": j.url} for j in jobs]}

@app.get("/export/excel")
def export(db: Session = Depends(get_db)):
    filepath = generate_excel(db)
    if filepath:
        return FileResponse(filepath, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                          filename=f'workday_jobs_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx')
    raise HTTPException(500)

@app.post("/jobs/{job_id}/status")
def update_status(job_id: int, status: str, notes: str = "", db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if app:
        app.status = status
        if notes:
            app.notes = notes
    else:
        app = Application(job_id=job_id, status=status, notes=notes)
        db.add(app)
    db.commit()
    return {"ok": True}

# ===== DEBUG ENDPOINTS =====
@app.get("/test-scrape")
def test_scrape_sync(db: Session = Depends(get_db)):
    """Run scrape SYNCHRONOUSLY for debugging - returns immediately with results"""
    print("\n" + "🧪"*30, flush=True)
    print("🧪 RUNNING SYNCHRONOUS TEST SCRAPE", flush=True)
    print("🧪"*30, flush=True)

    try:
        jobs = scrape_workday_with_playwright()

        # Save to DB
        new_count = 0
        for job in jobs[:5]: 
            try:
                existing = db.query(Job).filter(Job.url.contains(job['url'][:100])).first()
                if not existing:
                    new_job = Job(
                        title=job['title'],
                        company=job['company'],
                        url=job['url'],
                        location=job['location'],
                        description=job.get('description', ''),
                        source=job['source'],
                        found_date=datetime.utcnow(),
                        posted_date=job.get('posted_date', datetime.utcnow()),
                        notified=False
                    )
                    db.add(new_job)
                    new_count += 1
            except Exception as e:
                print(f"Error: {e}", flush=True)

        db.commit()

        return {
            "success": True,
            "jobs_scraped": len(jobs),
            "jobs_saved": new_count,
            "sample": jobs[:3] if jobs else []
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    """Test database connectivity and schema"""
    try:
        # Test connection
        result = db.execute(text("SELECT 1")).fetchone()

        # Count jobs
        job_count = db.query(Job).count()

        # Insert test job
        test_job = Job(
            title="TEST - Delete Me",
            company="TestCorp",
            url=f"https://test.com/job/{datetime.utcnow().timestamp()}",
            location="Test City",
            description="Test job for debugging",
            source="test",
            found_date=datetime.utcnow(),
            posted_date=datetime.utcnow(),
            notified=False
        )
        db.add(test_job)
        db.commit()

        new_count = db.query(Job).count()

        return {
            "success": True,
            "connection": "OK",
            "jobs_before": job_count,
            "jobs_after": new_count,
            "test_job_id": test_job.id,
            "message": "Database is working! Test job inserted."
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get scraping statistics"""
    try:
        total = db.query(Job).count()
        by_company = db.query(Job.company, func.count(Job.id)).group_by(Job.company).all()
        recent = db.query(Job).filter(
            Job.found_date > datetime.utcnow() - timedelta(hours=24)
        ).count()

        return {
            "total_jobs": total,
            "jobs_last_24h": recent,
            "by_company": {company: count for company, count in by_company}
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "time": datetime.utcnow().isoformat(),
        "database": "connected" if SessionLocal else "not initialized"
    }


@app.get("/test-simple")
def test_simple():
    """Simple test without browser - just verify Playwright import works"""
    try:
        from playwright.sync_api import sync_playwright
        import subprocess

        # Check if chromium is installed
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        chromium_path = result.stdout.strip() if result.returncode == 0 else "not found in PATH"

        # Check playwright browsers
        result2 = subprocess.run(['playwright', 'install', '--dry-run'], capture_output=True, text=True)

        return {
            "success": True,
            "playwright_import": "OK",
            "chromium_path": chromium_path,
            "playwright_check": result2.stdout[:500] if result2.stdout else result2.stderr[:500]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/test-playwright")
def test_playwright():
    """Test if Playwright can launch browser in Docker"""
    import os
    import time
    import threading
    
    print("🧪 Starting Playwright test...", flush=True)
    start_time = time.time()
    
    try:
        from playwright.sync_api import sync_playwright
        
        print(f"[{time.time() - start_time:.1f}s] Import successful", flush=True)
        
        # Run browser launch in a thread with timeout
        result = {"success": False, "error": "Timeout"}
        
        def run_browser():
            try:
                with sync_playwright() as p:
                    print(f"[{time.time() - start_time:.1f}s] Launching Chromium...", flush=True)
                    
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--single-process'
                        ],
                        timeout=15000
                    )
                    
                    print(f"[{time.time() - start_time:.1f}s] Browser launched: {browser.version}", flush=True)
                    
                    # Try a simple data URL first (no network required)
                    page = browser.new_page()
                    page.goto('data:text/html,<h1>Test Page</h1>', timeout=5000)
                    title = page.title()
                    
                    print(f"[{time.time() - start_time:.1f}s] Simple page loaded: {title}", flush=True)
                    
                    browser.close()
                    
                    result.update({
                        "success": True,
                        "title": title,
                        "browser_version": browser.version,
                        "time_elapsed": f"{time.time() - start_time:.2f}s",
                        "message": "Playwright works!"
                    })
                    
            except Exception as e:
                import traceback
                result.update({
                    "success": False,
                    "error": str(e),
                    "traceback": traceback.format_exc()[:500]
                })
        
        # Run with timeout
        thread = threading.Thread(target=run_browser)
        thread.start()
        thread.join(timeout=30)  # 30 second timeout
        
        if thread.is_alive():
            print(f"[{time.time() - start_time:.1f}s] Test timed out after 30 seconds", flush=True)
            return {
                "success": False,
                "error": "Timeout after 30 seconds",
                "time_elapsed": f"{time.time() - start_time:.2f}s",
                "message": "Browser launch is hanging. Check Docker resources."
            }
        
        return result
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"❌ Global error: {error_msg}", flush=True)
        
        return {
            "success": False,
            "error": error_msg,
            "traceback": traceback.format_exc()[:500],
            "time_elapsed": f"{time.time() - start_time:.2f}s"
        }
@app.get("/debug-playwright")
def debug_playwright():
    """Debug Playwright installation"""
    import subprocess
    import os
    
    results = {}
    
    # Check system
    results['cwd'] = os.getcwd()
    
    # Check Playwright import
    try:
        import playwright
        results['playwright_version'] = playwright.__version__
    except ImportError as e:
        results['playwright_import_error'] = str(e)
    
    # Check /ms-playwright directory
    try:
        result = subprocess.run(['ls', '-la', '/ms-playwright/'], 
                              capture_output=True, text=True)
        results['ms_playwright_dir'] = result.stdout[:500]
    except Exception as e:
        results['ms_playwright_dir_error'] = str(e)
    
    # Check chromium specifically
    try:
        result = subprocess.run(['ls', '-la', '/ms-playwright/chromium-1091/'], 
                              capture_output=True, text=True)
        results['chromium_dir'] = result.stdout[:500]
    except Exception as e:
        results['chromium_dir_error'] = str(e)
    
    return results

@app.get("/test-playwright-minimal")
def test_playwright_minimal():
    """Minimal test - just check if browser can launch"""
    try:
        from playwright.sync_api import sync_playwright
        import time
        
        start = time.time()
        
        print("Starting minimal Playwright test...", flush=True)
        
        # Just launch and close, no navigation
        with sync_playwright() as p:
            print("Launching browser...", flush=True)
            browser = p.chromium.launch(
                headless=True,
                timeout=10000,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            elapsed = time.time() - start
            print(f"Browser launched in {elapsed:.2f}s", flush=True)
            print(f"Browser version: {browser.version}", flush=True)
            
            browser.close()
            
        return {
            "success": True,
            "time": f"{time.time() - start:.2f}s",
            "message": "Browser launched successfully"
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Error in minimal test: {error_msg}", flush=True)
        return {
            "success": False,
            "error": error_msg,
            "traceback": traceback.format_exc()[:500]
        }

@app.get("/test-playwright-fixed")
def test_playwright_fixed():
    """GUARANTEED working Playwright test"""
    import time
    import subprocess
    import os
    
    start = time.time()
    
    try:
        print("🧪 Starting guaranteed Playwright test...", flush=True)
        from playwright.sync_api import sync_playwright
        
        print(f"[{time.time()-start:.1f}s] Playwright imported", flush=True)
        
        with sync_playwright() as p:
            print(f"[{time.time()-start:.1f}s] Launching Firefox with NO arguments...", flush=True)
            
            # Simple launch
            browser = p.firefox.launch(
                headless=True,
                timeout=25000  
                
            )
            
            print(f"[{time.time()-start:.1f}s] SUCCESS! Firefox launched", flush=True)
            print(f"[{time.time()-start:.1f}s] Version: {browser.version}", flush=True)
            
            # Quick test
            page = browser.new_page()
            page.goto('data:text/html,<h1>JobScout Test</h1>', timeout=5000)
            title = page.title()
            
            browser.close()
            
            return {
                "success": True,
                "title": title,
                "browser": "firefox",
                "version": browser.version,
                "time": f"{time.time()-start:.2f}s",
                "message": "Playwright WORKS in Docker!"
            }
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[{time.time()-start:.1f}s] ERROR: {error_msg}", flush=True)
        
        # Diagnostic info
        diag = {
            "cwd": os.getcwd(),
            "playwright_browsers": "Checking..."
        }
        
        try:
            # Check if browsers are installed
            result = subprocess.run(['ls', '-la', '/ms-playwright/'], 
                                  capture_output=True, text=True, timeout=5)
            diag["playwright_browsers"] = result.stdout[:200] if result.stdout else "Not found"
        except:
            diag["playwright_browsers"] = "Check failed"
        
        return {
            "success": False,
            "error": error_msg,
            "diagnostic": diag,
            "time": f"{time.time()-start:.2f}s",
            "recommendation": "Try launching with no extra arguments"
        }
        
@app.get("/diagnose-playwright")
def diagnose_playwright():
    """Diagnose Playwright installation in container"""
    import subprocess
    import os
    
    checks = {}
    
    # 1. Check image
    checks['docker_image'] = "Microsoft Playwright Python Image"
    
    # 2. Check environment variables
    checks['env_playwright_path'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 'Not set')
    
    # 3. Check installed browsers
    try:
        result = subprocess.run(['ls', '-la', '/ms-playwright/'], 
                               capture_output=True, text=True)
        checks['ms_playwright_dir'] = result.stdout[:500]
    except Exception as e:
        checks['ms_playwright_dir_error'] = str(e)
    
    # 4. Check chromium
    try:
        result = subprocess.run(['which', 'chromium'], 
                               capture_output=True, text=True)
        checks['chromium_path'] = result.stdout.strip()
    except Exception as e:
        checks['chromium_path_error'] = str(e)
    
    # 5. Check playwright command
    try:
        result = subprocess.run(['playwright', '--version'], 
                               capture_output=True, text=True)
        checks['playwright_version'] = result.stdout.strip()
    except Exception as e:
        checks['playwright_version_error'] = str(e)
    
    # 6. Check Python import
    try:
        from playwright.sync_api import sync_playwright
        checks['python_import'] = "SUCCESS"
        
        # Try launch
        with sync_playwright() as p:
            checks['playwright_context'] = "SUCCESS"
    except Exception as e:
        checks['python_import_error'] = str(e)
    
    return checks


# ===== TELEGRAM BOT COMPATIBILITY ENDPOINTS =====
@app.get("/api/jobs/search")
def telegram_search(q: str = "", db: Session = Depends(get_db)):
    """Simple search for Telegram bot"""
    jobs = db.query(Job).filter(
        Job.title.ilike(f"%{q}%") if q else True
    ).filter(
        Job.is_internship == True
    ).order_by(Job.posted_date.desc()).limit(5).all()
    
    return [{
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "url": j.url,
        "date_posted": "Recent",
        "source": j.source
    } for j in jobs]

@app.get("/api/jobs/latest")
def telegram_latest(db: Session = Depends(get_db)):
    """Latest jobs for Telegram bot"""
    jobs = db.query(Job).filter(
        Job.is_internship == True
    ).order_by(Job.posted_date.desc()).limit(5).all()
    
    return [{
        "title": j.title,
        "company": j.company,
        "location": j.location
    } for j in jobs]

@app.get("/test-wsl-memory")
def test_wsl_memory():
    """Test WSL memory configuration"""
    import os
    import subprocess
    
    try:
        # Check memory inside container
        result = subprocess.run(
            ['free', '-h'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return {
            "success": True,
            "memory_info": result.stdout if result.stdout else "Could not get memory info",
            "wsl_config_set": "Yes" if os.path.exists('/.dockerenv') else "Unknown",
            "message": "Check if memory=8GB is working"
        }
    except:
        return {
            "success": False,
            "message": "Run docker-compose up first"
        }

@app.get("/api/health")
def telegram_health():
    return {"status": "ok", "service": "JobScout"}

# ===== SCHEDULER =====

# Auto-scrape every 30 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(run_scrape, 'interval', minutes=30)
scheduler.start()

print("Scheduler started - scraping every 30 minutes", flush=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)