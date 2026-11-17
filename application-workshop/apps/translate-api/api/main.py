#!/usr/bin/env python3

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Translation API microservice for the GitOps Application Workshop.

Provides a REST API (/translate, /api, /healthz) backed by Google Cloud Translation API v2
with an automatic air-gapped local fallback for disconnected GDC Sandbox environments,
plus optional Keycloak OIDC Bearer token verification.
"""

import base64
import json
import logging
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, jsonify, request
import requests

load_dotenv()

app = Flask(__name__)

TRANSLATE_API_URL = os.environ.get(
    "TRANSLATE_API_URL", "https://translation.googleapis.com/language/translate/v2"
)
TRANSLATE_APP_API_KEY = os.environ.get("TRANSLATE_APP_API_KEY", "").strip()
KEYCLOAK_INTERNAL_URL = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "sandbox")

PLACEHOLDER_KEYS = {
    "",
    "sample-key-12345",
    "YOUR_TRANSLATE_API_KEY",
    "airgapped-offline",
    "changeme",
}

OFFLINE_DICTIONARY = {
    "es": {
        "name": "Spanish",
        "phrases": {
            "hello": "Hola",
            "hello world": "Hola Mundo",
            "good morning": "Buenos días",
            "thank you": "Gracias",
            "welcome to google distributed cloud": "Bienvenido a Google Distributed Cloud",
            "mission status ready": "Estado de la misión listo",
        },
        "prefix": "[ES Traducción]",
    },
    "fr": {
        "name": "French",
        "phrases": {
            "hello": "Bonjour",
            "hello world": "Bonjour le monde",
            "good morning": "Bonjour",
            "thank you": "Merci",
            "welcome to google distributed cloud": "Bienvenue sur Google Distributed Cloud",
            "mission status ready": "Statut de la mission prêt",
        },
        "prefix": "[FR Traduction]",
    },
    "de": {
        "name": "German",
        "phrases": {
            "hello": "Hallo",
            "hello world": "Hallo Welt",
            "good morning": "Guten Morgen",
            "thank you": "Danke",
            "welcome to google distributed cloud": "Willkommen bei Google Distributed Cloud",
            "mission status ready": "Missionsstatus bereit",
        },
        "prefix": "[DE Übersetzung]",
    },
    "it": {
        "name": "Italian",
        "phrases": {
            "hello": "Ciao",
            "hello world": "Ciao mondo",
            "good morning": "Buongiorno",
            "thank you": "Grazie",
            "welcome to google distributed cloud": "Benvenuti in Google Distributed Cloud",
            "mission status ready": "Stato della missione pronto",
        },
        "prefix": "[IT Traduzione]",
    },
    "ja": {
        "name": "Japanese",
        "phrases": {
            "hello": "こんにちは (Konnichiwa)",
            "hello world": "ハロー・ワールド (Hello World)",
            "good morning": "おはようございます (Ohayou gozaimasu)",
            "thank you": "ありがとうございます (Arigatou gozaimasu)",
            "welcome to google distributed cloud": "Google Distributed Cloud へようこそ",
            "mission status ready": "ミッション準備完了",
        },
        "prefix": "[JA 翻訳]",
    },
    "zh": {
        "name": "Chinese",
        "phrases": {
            "hello": "你好 (Nǐ hǎo)",
            "hello world": "你好，世界 (Hello World)",
            "good morning": "早上好 (Zǎoshang hǎo)",
            "thank you": "谢谢 (Xièxiè)",
            "welcome to google distributed cloud": "欢迎使用 Google Distributed Cloud",
            "mission status ready": "任务状态就绪",
        },
        "prefix": "[ZH 翻译]",
    },
    "ru": {
        "name": "Russian",
        "phrases": {
            "hello": "Привет (Privet)",
            "hello world": "Привет, мир (Hello World)",
            "good morning": "Доброе утро (Dobroye utro)",
            "thank you": "Спасибо (Spasibo)",
            "welcome to google distributed cloud": "Добро пожаловать в Google Distributed Cloud",
            "mission status ready": "Статус миссии: готов",
        },
        "prefix": "[RU Перевод]",
    },
    "en": {
        "name": "English",
        "phrases": {},
        "prefix": "[EN Translation]",
    },
}

logging.basicConfig(level=logging.INFO)


def translate_offline(text: str, target_language: str) -> dict:
    """Provide deterministic offline translation for air-gapped GDC Sandbox environments."""
    lang_cfg = OFFLINE_DICTIONARY.get(target_language, OFFLINE_DICTIONARY["es"])
    normalized = text.strip().lower().rstrip("!.,?")
    if target_language == "en":
        translated = text
    elif normalized in lang_cfg["phrases"]:
        translated = lang_cfg["phrases"][normalized]
    else:
        translated = f"{lang_cfg['prefix']} {text}"
    return {
        "translatedText": translated,
        "detectedSourceLanguage": "en",
        "mode": "airgapped-local",
    }


def verify_keycloak_token(auth_header, incoming_headers=None):
    """Verify Bearer token against Keycloak's /userinfo endpoint."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return {
            "verified": False,
            "mode": "standalone",
            "message": "Running in standalone mode (no OIDC Bearer token provided)",
        }

    token = auth_header.split(" ", 1)[1].strip()
    userinfo_url = (
        f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/userinfo"
    )
    req_headers = {"Authorization": f"Bearer {token}"}

    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            token_iss = claims.get("iss")
            if token_iss:
                parsed_iss = urlparse(token_iss)
                if parsed_iss.netloc:
                    req_headers["X-Forwarded-Host"] = parsed_iss.netloc
                    req_headers["X-Forwarded-Proto"] = parsed_iss.scheme or "http"
    except Exception as exc:
        app.logger.warning(f"Could not parse token claims for issuer: {exc}")

    try:
        resp = requests.get(userinfo_url, headers=req_headers, timeout=3)
        if resp.status_code == 200:
            userinfo = resp.json()
            return {
                "verified": True,
                "mode": "keycloak",
                "issuer": f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}",
                "username": userinfo.get("preferred_username") or userinfo.get("name"),
                "email": userinfo.get("email"),
                "nationality": userinfo.get("nationality"),
                "clearance": userinfo.get("clearance"),
                "service_branch": userinfo.get("service_branch"),
                "rank": userinfo.get("rank"),
                "rank_grade": userinfo.get("rank_grade"),
                "coi": userinfo.get("coi"),
                "mission_id": userinfo.get("mission_id"),
                "sub": userinfo.get("sub"),
            }
        return {
            "verified": False,
            "mode": "keycloak",
            "error": f"Token rejected by Keycloak (HTTP {resp.status_code})",
        }
    except Exception as exc:
        app.logger.warning(f"Failed to contact Keycloak at {userinfo_url}: {exc}")
        return {
            "verified": False,
            "mode": "keycloak_unreachable",
            "error": str(exc),
        }


@app.route("/healthz", methods=["GET"])
def healthz():
    """Kubernetes liveness and readiness probe endpoint."""
    return jsonify({"status": "healthy", "service": "translate-api"}), 200


@app.route("/", methods=["GET"])
def home():
    """Return service metadata for API inspection."""
    app.logger.info("Running GET /")
    return jsonify(
        {
            "_message": "This is the translate-api GitOps application.",
            "service": "translate-api",
            "status": "ready",
            "request": {
                "headers": {"User-Agent": request.headers.get("User-Agent")},
                "args": request.args,
                "origin": request.remote_addr,
            },
        }
    )


@app.route("/translate", methods=["POST"])
def translate_text():
    """Translate input text into target_language via Cloud Translation API or air-gapped fallback."""
    app.logger.info("Running POST /translate")

    try:
        data = request.get_json(silent=True) or {}
        text_to_translate = data.get("text")
        target_language = data.get("target_language") or data.get("target") or "es"

        if not text_to_translate:
            return jsonify({"error": 'Missing "text" in request body'}), 400

        auth_header = request.headers.get("Authorization")
        auth_info = verify_keycloak_token(auth_header, request.headers)

        # Use offline air-gapped engine if placeholder API key is configured
        if TRANSLATE_APP_API_KEY in PLACEHOLDER_KEYS:
            app.logger.info(
                "Using air-gapped local translation engine (placeholder API key configured)."
            )
            offline_res = translate_offline(text_to_translate, target_language)
            return jsonify(
                {
                    "original_text": text_to_translate,
                    "translated_text": offline_res["translatedText"],
                    "detected_source_language": offline_res["detectedSourceLanguage"],
                    "translation_mode": offline_res["mode"],
                    "access_verification": auth_info,
                }
            )

        params = {
            "key": TRANSLATE_APP_API_KEY,
            "q": text_to_translate,
            "target": target_language,
        }

        try:
            response = requests.post(TRANSLATE_API_URL, params=params, timeout=5)
            response.raise_for_status()
            result = response.json()
            if (
                "data" in result
                and "translations" in result["data"]
                and len(result["data"]["translations"]) > 0
            ):
                translation_info = result["data"]["translations"][0]
                return jsonify(
                    {
                        "original_text": text_to_translate,
                        "translated_text": translation_info["translatedText"],
                        "detected_source_language": translation_info.get(
                            "detectedSourceLanguage"
                        ),
                        "translation_mode": "cloud-translation-api",
                        "access_verification": auth_info,
                    }
                )
        except requests.exceptions.RequestException as req_err:
            app.logger.warning(
                f"Cloud Translation API unreachable ({req_err}); falling back to air-gapped engine."
            )
            offline_res = translate_offline(text_to_translate, target_language)
            return jsonify(
                {
                    "original_text": text_to_translate,
                    "translated_text": offline_res["translatedText"],
                    "detected_source_language": offline_res["detectedSourceLanguage"],
                    "translation_mode": offline_res["mode"],
                    "access_verification": auth_info,
                }
            )

        return (
            jsonify(
                {
                    "error": "Unexpected response format from Translation API",
                    "details": result,
                }
            ),
            500,
        )

    except Exception as exc:
        app.logger.error(f"Error during translation: {exc}")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=port)
