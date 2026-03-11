import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_URL = os.getenv("API_URL", "http://backend:8000")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message when /start is issued."""
    user = update.effective_user
    welcome_text = f"""
     Hello {user.first_name}!
    
     *Welcome to JobScout Bot*
    
    I can help you find job opportunities!
    
    *Available Commands:*
    /start - Welcome message
    /search - Search for jobs
    /latest - Get latest job postings
    /help - Show help message
    
    Try: `/search python developer`
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message when /help is issued."""
    help_text = """
     *JobScout Bot Help*
    
    *Commands:*
    /start - Welcome message
    /search <keywords> - Search for jobs
    Example: `/search python remote`
    /latest - Get latest 10 job postings
    /help - This help message
    
    *How to use:*
    1. Use /search followed by job keywords
    2. I'll search through available jobs
    3. Get detailed job information
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command."""
    if not context.args:
        await update.message.reply_text(
            "Please specify job keywords!\nExample: `/search python developer remote`",
            parse_mode='Markdown'
        )
        return
    
    query = " ".join(context.args)
    user = update.effective_user
    
    await update.message.reply_text(f"🔍 Searching for: *{query}*...", parse_mode='Markdown')
    
    try:
        # Call backend API
        response = requests.get(f"{API_URL}/api/jobs/search", params={"q": query})
        
        if response.status_code == 200:
            jobs = response.json()
            if jobs:
                message = f"✅ Found {len(jobs)} jobs for '*{query}*':\n\n"
                for job in jobs[:5]:  # Show first 5 results
                    message += f"🏢 *{job.get('title', 'N/A')}*\n"
                    message += f"📍 {job.get('location', 'Remote')}\n"
                    message += f"🔗 {job.get('company', 'Company')}\n"
                    message += f"📅 {job.get('date_posted', 'N/A')}\n"
                    message += "━━━━━━━━━━━━━━\n\n"
                
                if len(jobs) > 5:
                    message += f"... and {len(jobs) - 5} more results"
            else:
                message = f"❌ No jobs found for '*{query}*'\n\nTry different keywords!"
        else:
            message = "⚠️ Could not connect to job database. Please try again later."
    
    except Exception as e:
        logger.error(f"Error searching jobs: {e}")
        message = f"🔧 *Backend Connection*\n\nYour backend is running at: {API_URL}\n\nTry connecting to it first!"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get latest job postings."""
    await update.message.reply_text("📊 Fetching latest job postings...", parse_mode='Markdown')
    
    try:
        response = requests.get(f"{API_URL}/api/jobs/latest")
        
        if response.status_code == 200:
            jobs = response.json()
            if jobs:
                message = f"📈 *Latest {len(jobs)} Job Postings:*\n\n"
                for job in jobs[:10]:
                    message += f"• {job.get('title', 'N/A')} at {job.get('company', 'N/A')}\n"
            else:
                message = "No job postings available yet."
        else:
            message = f"Backend API status: {response.status_code}"
    
    except Exception as e:
        logger.error(f"Error fetching latest jobs: {e}")
        message = f"⚙️ *Backend Status*\n\nConnect to: {API_URL}\n\nMake sure your backend is running!"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echo user message for testing."""
    await update.message.reply_text(f"You said: {update.message.text}")

def main():
    """Start the bot."""
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    
    print(f"Bot token: {TOKEN[:10]}...")
    print(f"API URL: {API_URL}")
    
    # Create Application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Start the bot
    logger.info("Starting Telegram bot...")
    print("Bot is starting, polling for messages...")
    print("Ready. Message your bot on Telegram: @jobscout_NawalF_bot")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()