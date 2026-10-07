.PHONY: data train api web all
PY=.venv/bin/python
data:   ; $(PY) data/generate.py
train:  ; $(PY) ml/train.py
api:    ; .venv/bin/uvicorn api.main:app --port 8000 --reload
web:    ; cd web && npm run dev
setup:  ; uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python pandas numpy scikit-learn lightgbm shap fastapi uvicorn pyarrow matplotlib httpx anthropic python-dotenv && cd web && npm install
all: data train
