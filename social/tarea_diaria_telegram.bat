@echo off
REM Tarea programada diaria (7:00 AM) -- 1 hora despues del pipeline de
REM GitHub Actions (6:00 AM Peru). Jala los picks frescos del repo antes
REM de generar/publicar el mensaje, porque el pipeline actualiza
REM Data/picks_hoy.json en GitHub, no directamente en esta copia local.
cd /d "C:\Users\PC\SportPicks-Ligas"
git pull origin main
"C:\Users\PC\SportPicks-Ligas\venv\Scripts\python.exe" "C:\Users\PC\SportPicks-Ligas\social\generar_mensaje_telegram.py" --publicar

REM Prompts de IA (Nano Banana Pro + Flow) para el post diario de
REM redes -- se generan solos cada mañana en Data/social/<fecha>/
REM prompts_ia.txt, listos para copiar/pegar. No requiere credenciales,
REM solo el historial_picks.csv que el git pull de arriba ya trajo
REM fresco.
"C:\Users\PC\SportPicks-Ligas\venv\Scripts\python.exe" "C:\Users\PC\SportPicks-Ligas\social\generar_prompts_ia.py"
