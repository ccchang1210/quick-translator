@echo off
echo ============================================
echo  Quick Translator - Memory Usage Report
echo ============================================
echo.
echo [Python processes]
tasklist /FO TABLE /FI "IMAGENAME eq python.exe" 2>nul
tasklist /FO TABLE /FI "IMAGENAME eq pythonw.exe" 2>nul
tasklist /FO TABLE /FI "IMAGENAME eq pyw.exe" 2>nul
echo.
echo [Ollama processes]
tasklist /FO TABLE /FI "IMAGENAME eq ollama.exe" 2>nul
echo.
echo [System RAM summary]
wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /VALUE 2>nul
echo.
pause
