## Lab 1 - Deploy HTML Server

For context, we'll review ku alias, build script, and kustomization. 

1. On sandbox bootstrapper, login. 

Confirm `.env` settings. 

```bash
cat .env
```
Login

```bash
cd ~/gdc-ag/gdc-sandbox-workshop
source .env
login
```
Make sure `harbor-secret` from docker login is set as a secret. 
```bash
ku create secret docker-registry harbor-secret --from-file=.dockerconfigjson=$HOME/.docker/config.json
```

2. Build and deploy service

```bash
build ./workloads/web-server/app web-server
# show harbor

# change repo name "[PROJECT_NAME]" in app.properties
vi workloads/web-server/base/cluster/app.properties

ku apply -k workloads/web-server/base/cluster
```

Inspect
```bash
ku get pods
ku get svc
```
Get webserver ip address
```bash
export WEBSERVER_IP=$(ku get svc -l app-name=web-server -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
echo $WEBSERVER_IP
echo "curl -X GET http://$WEBSERVER_IP"
```

3. Test over ssh

```bash
curl -X GET http://<ipaddress>
```

4. Make a change and redeploy. 

```bash
vi workloads/web-server/app/index.html 
build ./workloads/web-server/app web-server
ku rollout restart deploy web-server

```
3. ReTest over ssh

```bash
curl -X GET http://<ipaddress>
```
