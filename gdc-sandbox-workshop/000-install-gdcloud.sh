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

cd ~

mv ~/Downloads/gdcloud_cli.tar.gz .
tar -xf gdcloud_cli.tar.gz

echo 'export PATH=$PATH:~/google-distributed-cloud-hosted-cli/bin' >> ~/.bashrc
source ~/.bashrc

gdcloud config set core/organization_console_url https://console.org-1.zone1.google.gdch.test
gdcloud components install gdcloud-k8s-auth-plugin
gdcloud components install storage-cli-dependencies

echo -n | openssl s_client -showcerts -connect console.org-1.zone1.google.gdch.test:443 | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > org-1-web-tls-ca.cert

curl -k https://console.org-1.zone1.google.gdch.test/.well-known/login-config | grep certificateAuthorityData | head -1 | cut -d : -f 2 | awk '{print $1}' | sed 's/"//g' | base64 --decode > trusted_certs.crt
