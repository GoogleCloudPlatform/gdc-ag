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

docker_pull() {
    docker pull $1
    docker tag $1 $HARBOR_URL/$HARBOR_PROJECT/$2:latest
    docker push $HARBOR_URL/$HARBOR_PROJECT/$2:latest
}

docker_build() {
    docker build -t $2 $1
    docker tag $2:latest $HARBOR_URL/$HARBOR_PROJECT/$2:latest
    docker push $HARBOR_URL/$HARBOR_PROJECT/$2:latest
}


ku() {
    kubectl --kubeconfig ${HOME}/${CLUSTER_NAME}-kubeconfig -n ${NAMESPACE} $@
}
    
ko() {
    kubectl --kubeconfig ${HOME}/org-1-admin-kubeconfig -n ${NAMESPACE} $@
}

kp() {
    kubectl --kubeconfig ${HOME}/org-1-admin-kubeconfig -n platform $@
}

kustomize() {
    if [ "$2" = "kustomize/projects" ]; then
        kp apply -k $@
    else
        ku apply -k $@
    fi
}

apply() {
    if [ "$2" = "platform" ]; then
        for f in $1/*.yaml; do envsubst < $f | ko -n "platform" apply -f -; done
    else
        for f in $1/*.yaml; do envsubst < $f | ku apply -f -; done
    fi
}

delete() {
    if [ "$2" = "platform" ]; then
        for f in $1/*.yaml; do envsubst < $f | ko -n "platform" delete -f -; done
    else
        for f in $1/*.yaml; do envsubst < $f | ku delete -f -; done
    fi    
}

restart() {
    if [ "$2" = "platform" ]; then
        for f in $1/*.yaml; do envsubst < $f | ko -n "platform" rollout restart -f -; done
    else
        for f in $1/*.yaml; do envsubst < $f | ku rollout restart -f -; done
    fi
}

