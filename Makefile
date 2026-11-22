.PHONY: run test eval docker-build docker-up

run:
	cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	cd backend && MORI_STREAM_DELAY=0 python -m unittest discover -s tests -v

eval:
	cd backend && python eval/run_eval.py --check

docker-build:
	docker build -t mori:local .

docker-up:
	docker compose up --build
