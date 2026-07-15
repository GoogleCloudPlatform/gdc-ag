# Copyright 2025 Google LLC
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


import os
import requests # Use requests for HTTP calls
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)

TRANSLATE_API_URL = 'https://translation.googleapis.com/language/translate/v2'
TRANSLATE_APP_API_KEY = os.environ['TRANSLATE_APP_API_KEY']

logging.basicConfig(level=logging.INFO) # Set the desired logging level


@app.route('/', methods=['GET'])
def home():
    
    app.logger.info("Running GET /")
    app.logger.info({"request":{"headers":{"User-Agent":request.headers.get('User-Agent')},
                                "args":request.args,
                                "origin":request.remote_addr,
                               }})

    return jsonify({"_message":"This is the translate app.", 
                    "request":{"headers":{"User-Agent":request.headers.get('User-Agent')},
                                "args":request.args,
                                "origin":request.remote_addr,
                               }})


@app.route('/translate', methods=['POST'])
def translate_text():

    app.logger.info("Running POST /translate")

    try:
        data = request.get_json()
        text_to_translate = data.get('text')
        target_language = data.get('target_language', 'en') # Default to English
    
        if not text_to_translate:
            return jsonify({'error': 'Missing "text" in request body'}), 400

        params = {
            'key': TRANSLATE_APP_API_KEY, 
            'q': text_to_translate,
            'target': target_language
        }

        app.logger.info(f"Requested language: {target_language}")
        app.logger.info(f"Text to translate: {text_to_translate}")

        response = requests.post(TRANSLATE_API_URL, params=params)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        result = response.json()

        # The structure of the response from the REST API is slightly different
        # It's usually: {'data': {'translations': [{'translatedText': '...', 'detectedSourceLanguage': '...'}]}}
        if 'data' in result and 'translations' in result['data'] and len(result['data']['translations']) > 0:
            translation_info = result['data']['translations'][0]
            response = jsonify({
                'original_text': text_to_translate,
                'translated_text': translation_info['translatedText'],
                'detected_source_language': translation_info.get('detectedSourceLanguage')
            })
            app.logger.info(response)
            return response
        else:
            return jsonify({'error': 'Unexpected response format from Translation API', 'details': result}), 500

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
        return jsonify({'error': f"Translation API request failed: {http_err}", 'details': response.text}), response.status_code
    except Exception as e:
        print(f"Error during translation: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
