## Lab 3 - Deploy Elasticsearch


1. Follow Step 1 on [Lab 1](LAB-1.md).

2. Build and deploy service

```bash
pull "elasticsearch:8.11.4" "elasticsearch"
pull "kibana:8.11.4" "kibana"
pull "busybox:latest" "busybox"

# show harbor

# change repo name "[PROJECT_NAME]" in app.properties
vi workloads/elastic/base/cluster/app.properties

ku apply -k workloads/elastic/base/cluster

```

Inspect
```bash
ku get pods
ku get svc
```

Get webserver ip address
```bash
export KIBANA_IP=$(ku get svc -l app=kibana -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
echo $KIBANA_IP

ku logs $(ku get pods -l app=kibana -o jsonpath='{.items[0].metadata.name}')

```

6. Test in browser over ssh
