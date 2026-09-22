up:
	docker compose up --build -d
down:
	docker compose down -v
demo:
	bash scripts/run_demo.sh
test:
	python -m pytest -q
campaign:
	python scripts/run_campaign.py
report:
	python scripts/generate_report.py
