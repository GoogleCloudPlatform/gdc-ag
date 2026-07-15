# Translate App

## Local dev

```bash
cd workloads/translate-api/app
uv venv
uv pip install -r requirements.txt
export TRANSLATE_APP_API_KEY=aaaaaaa

```

## Setup

```bash

```


```bash

export TRANSLATION_IP=10.200.32.97
curl -X POST -H "Content-Type: application/json" -d '{"text": "Hello, world!", "target_language": "es"}' http://${TRANSLATION_IP}/translate

curl -X POST -H "Content-Type: application/json" -d '{"text": "Hello, world!", "target_language": "es"}' http://0.0.0.0:8080/translate

```