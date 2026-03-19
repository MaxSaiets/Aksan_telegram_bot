"""
One-command launcher: kills old processes, flushes Redis, starts celery + uvicorn.

Usage:
    python start.py
"""
import subprocess
import sys
import time
import os

VENV_PYTHON = os.path.join(os.path.dirname(__file__), "venv", "Scripts", "python.exe")
PROJECT_DIR = os.path.dirname(__file__)


def kill_old():
    """Kill all python processes using port 8000 or running celery worker."""
    print("[1/4] Killing old processes...")
    ps_script = (
        'Get-CimInstance Win32_Process | '
        'Where-Object { $_.Name -eq "python.exe" -and '
        '($_.CommandLine -like "*uvicorn main:app*" -or $_.CommandLine -like "*celery*worker*") } | '
        'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; '
        'Write-Host "  Killed PID $($_.ProcessId)" }'
    )
    subprocess.run(["powershell", "-Command", ps_script], check=False)

    # Also kill by port 8000
    ps_port = (
        'Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | '
        'Where-Object { $_.OwningProcess -ne 0 } | '
        'ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue; '
        'Write-Host "  Killed port 8000 holder PID $($_.OwningProcess)" }'
    )
    subprocess.run(["powershell", "-Command", ps_port], check=False)
    time.sleep(1)


def flush_redis():
    """Clear stale celery tasks from Redis."""
    print("[2/4] Flushing Redis...")
    subprocess.run(
        [VENV_PYTHON, "-c", "import redis; r=redis.Redis(); r.flushdb(); print('  Redis flushed')"],
        check=False,
    )


def start_celery():
    """Start celery worker in background."""
    print("[3/4] Starting Celery worker...")
    proc = subprocess.Popen(
        [VENV_PYTHON, "-m", "celery", "-A", "app.tasks.celery_app", "worker",
         "--loglevel=info", "--pool=solo"],
        cwd=PROJECT_DIR,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print(f"  Celery PID: {proc.pid}")
    return proc


def start_uvicorn():
    """Start uvicorn (blocking — runs in foreground)."""
    print("[4/4] Starting Uvicorn on port 8000...")
    print("=" * 50)
    print("Bot is running! Press Ctrl+C to stop.")
    print("=" * 50)
    try:
        subprocess.run(
            [VENV_PYTHON, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=PROJECT_DIR,
        )
    except KeyboardInterrupt:
        pass


def main():
    kill_old()
    flush_redis()
    celery_proc = start_celery()
    time.sleep(2)  # let celery connect to Redis

    try:
        start_uvicorn()
    finally:
        print("\nStopping Celery...")
        celery_proc.terminate()
        celery_proc.wait(timeout=5)
        print("Done.")


if __name__ == "__main__":
    main()
