#!/bin/bash 

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


source .env

gdcloud auth login --login-config-cert=$HOME/org-1-web-tls-ca.cert

KUBECONFIG=${HOME}/${CLUSTER_NAME}-kubeconfig gdcloud clusters get-credentials ${CLUSTER_NAME} --zone zone1
KUBECONFIG=${HOME}/org-1-admin-kubeconfig gdcloud clusters get-credentials org-1-admin
KUBECONFIG=${HOME}/global-api-kubeconfig gdcloud clusters get-credentials global-api

echo $HARBOR_PASSWORD | docker login $HARBOR_URL_HTTPS -u $HARBOR_USERNAME --password-stdin
