# Ejecutar desde la raiz del repo (o: powershell -File scripts/celery-worker.ps1)
Set-Location $PSScriptRoot/..
& .\.venv\Scripts\python.exe -m celery -A workers.celery_app.celery_app worker -l info -P threads -c 4 --without-gossip --without-mingle --without-heartbeat
