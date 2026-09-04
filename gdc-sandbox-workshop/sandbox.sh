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

account=$(gcloud auth list  --filter=status:ACTIVE --format="value(account)")

if [ "$account" == "$USER_LDAP" ]; then
    echo "Logged in. "
    echo "$account"
else
    echo "Not logged in"
    gcloud auth login
fi

if [ "$1" == "tunnel" ]; then
    response=$(gcloud compute start-iap-tunnel \
        $SANDBOX_INSTANCE 3389 \
        --project=$SANDBOX_PROJECT \
        --zone=$SANDBOX_ZONE \
        --local-host-port=localhost:$SANDBOX_LOCAL_PORT_NUMBER)
    echo "Tunnel started on port $SANDBOX_LOCAL_PORT_NUMBER"
    echo $response
fi

if [ "$1" == "env" ]; then
    response=$(gcloud compute scp .env $SANDBOX_USER@$SANDBOX_INSTANCE:/home/$SANDBOX_USER/gdc-sandbox/.env \
        --tunnel-through-iap \
        --project $SANDBOX_PROJECT \
        --zone $SANDBOX_ZONE)
    exit 0
fi

if [ "$1" == "config" ]; then
    response=$(gcloud compute scp projects_config.yaml $SANDBOX_USER@$SANDBOX_INSTANCE:/home/$SANDBOX_USER/gdc-sandbox/projects_config.yaml \
        --tunnel-through-iap \
        --project $SANDBOX_PROJECT \
        --zone $SANDBOX_ZONE)
    exit 0
fi

if [ "$1" == "cp" ]; then
    response=$(gcloud compute scp $SANDBOX_INSTANCE:/home/$SANDBOX_USER/$2 $3 \
        --tunnel-through-iap \
        --project $SANDBOX_PROJECT \
        --zone $SANDBOX_ZONE)
    ls -la $3
    exit 0
fi

if [ "$1" == "ssh" ]; then
    response=$(sshuttle -r zone1-org-1-data@$SANDBOX_INSTANCE --no-latency-control \
        --ssh-cmd "gcloud compute ssh --project=$SANDBOX_PROJECT --zone=$SANDBOX_ZONE --tunnel-through-iap" \
        10.200.0.0/16 --dns)
fi