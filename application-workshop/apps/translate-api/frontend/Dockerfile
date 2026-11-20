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

# Stage 1: Build React 19 + MUI TypeScript Frontend
FROM node:22-slim AS frontend-builder
WORKDIR /frontend
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Non-Root Nginx Static Server & Reverse Proxy (:8080 -> :5000)
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-builder /frontend/dist /app/static

RUN mkdir -p /var/cache/nginx /var/log/nginx /tmp/nginx \
    && chown -R 1000:1000 /app /var/cache/nginx /var/log/nginx /tmp/nginx

USER 1000

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
