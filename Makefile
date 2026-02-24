VENV := .venv
PYTHON := $(VENV)/bin/python3

.PHONY: install auth run clean

$(VENV):
	python3 -m venv $(VENV)

install: $(VENV)
	$(PYTHON) -m pip install -e .

auth: install
	$(PYTHON) gtasks_mcp_server/server.py --auth

run: install
	$(PYTHON) -m gtasks_mcp_server

clean:
	rm -rf $(VENV) __pycache__ gtasks_mcp_server/__pycache__ *.egg-info build dist
