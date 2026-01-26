@echo off
echo ========================================
echo JOB SCOUT QUICK TEST
echo ========================================

echo Waiting for server to be ready...
timeout /t 10 /nobreak >nul

echo.
echo 1. Checking API...
curl http://localhost:8000/

echo.
echo 2. Checking health...
curl http://localhost:8000/health

echo.
echo 3. Clearing old jobs...
curl -X POST http://localhost:8000/clear-jobs

echo.
echo 4. Adding sample jobs...
curl -X POST http://localhost:8000/add-sample-jobs

echo.
echo 5. Checking current jobs...
curl http://localhost:8000/jobs

echo.
echo 6. Triggering scrape (background)...
curl -X POST http://localhost:8000/scrape

echo.
echo Waiting 20 seconds for scraping...
timeout /t 20 /nobreak >nul

echo.
echo 7. Checking jobs after scrape...
curl http://localhost:8000/jobs

echo.
echo 8. Getting stats...
curl http://localhost:8000/stats

echo.
echo 9. Downloading Excel file...
curl http://localhost:8000/export/excel -o "jobs.xlsx"

echo.
echo ========================================
echo DONE!
echo Check jobs.xlsx file in current folder
echo ========================================
pause