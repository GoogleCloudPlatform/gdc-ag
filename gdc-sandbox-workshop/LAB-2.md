## Lab 2 - Deploy API Translation Server


1. Follow Step 1 on [Lab 1](LAB-1.md).

2. Build and deploy service

```bash
build ./workloads/translate-api/app translate
# show harbor

# change repo name "[PROJECT_NAME]" in app.properties
vi workloads/translate-api/base/cluster/app.properties

mv workloads/translate-api/base/cluster/app-secrets.properties.example workloads/translate-api/base/cluster/app-secrets.properties

# change translate api key
vi workloads/translate-api/base/cluster/app-secrets.properties

ku apply -k workloads/translate-api/base/cluster
ko apply -k workloads/translate-api/base/org
```

Inspect
```bash
ku get pods
ku get svc
```

Get webserver ip address
```bash
export TRANSLATION_IP=$(ku get svc -l app-name=translation-app -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
echo $TRANSLATION_IP
echo "export TRANSLATION_IP=${TRANSLATION_IP}"

ku logs $(ku get pods -l app-name=translation-app -o jsonpath='{.items[0].metadata.name}')
```

```bash

curl -X GET http://$TRANSLATION_IP

curl -X POST -H 'Content-Type: application/json' -d '{"text": "Hello, world!", "target_language": "es"}' http://${TRANSLATION_IP}/translate

```

4. Review logs in Grafana. 

5. Make a change and redeploy. 

```bash
vi workloads/translate-api/app/main.py
build ./workloads/translate-api/app translate
ku rollout restart deploy translation-app

```
6. ReTest over ssh
