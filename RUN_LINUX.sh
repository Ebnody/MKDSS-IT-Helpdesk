#!/bin/sh
set -e
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py --host 0.0.0.0 --port 5000
