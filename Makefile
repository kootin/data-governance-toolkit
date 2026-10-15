.PHONY: install sample report test clean
install:
	pip install -e ".[dev]"
sample:
	python -m governance.sample
report: sample
	python -m governance.cli --out governance_report.md
test:
	pytest -q
clean:
	rm -rf sample_data governance_report.md
