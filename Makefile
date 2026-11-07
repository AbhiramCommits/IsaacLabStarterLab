PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else command -v python3; fi)
LAB := $(PYTHON) -m isaac_starter_lab.cli
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff
SEEDS ?= 0-199
EPISODE_SEEDS ?= 0-99

.PHONY: install lint test scene dr episode eval lab-headless check results clean docker-lab

install:
	$(PYTHON) -m pip install -r requirements.lock.txt
	$(PYTHON) -m pip install --no-deps -e .

lint:
	$(RUFF) check .

test:
	$(PYTEST) --cov=isaac_starter_lab --cov-report=term-missing --cov-fail-under=85

scene:
	mkdir -p artifacts
	$(LAB) scene --seed 7 --out artifacts/scene_seed7.usda

dr:
	$(LAB) dr --seeds $(SEEDS) --out datasets/dr --overwrite

episode:
	mkdir -p artifacts/episodes
	$(LAB) episode --seed 7 --backend kinematic --bridge localbus \
		--out artifacts/episodes/seed_7

eval:
	mkdir -p results
	$(LAB) eval perception --dataset datasets/dr --out results/perception_eval.json
	$(LAB) eval episodes --seeds $(EPISODE_SEEDS) --out results/episode_sweep.json

lab-headless:
	mkdir -p results artifacts
	$(PYTHON) scripts/run_lab_headless.py

check:
	mkdir -p results
	$(LAB) check all --root . --json-out results/labcheck.json

results:
	mkdir -p results
	$(PYTHON) scripts/collect_results.py

docker-lab:
	docker build -f docker/Dockerfile.lab -t isaac-starter-lab:local .

clean:
	rm -rf artifacts datasets/dr/images datasets/dr/labels .pytest_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
