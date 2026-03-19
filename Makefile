.PHONY: install run worker test lint docker-up docker-down

install:
	pip install -r requirements.txt

run:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload

worker:
	celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2

flower:
	celery -A app.tasks.celery_app flower --port=5555

test:
	pytest tests/ -v --tb=short

test-coverage:
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

lint:
	python -m py_compile config.py main.py
	find app -name "*.py" -exec python -m py_compile {} \;
	echo "Syntax OK"

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

ngrok:
	ngrok http 8000
