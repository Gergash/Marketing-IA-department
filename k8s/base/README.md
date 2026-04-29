# Kubernetes base manifests (post-MVP)

These manifests prepare deployment of API + Celery worker + Go publisher.

## Apply
```bash
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/configmap.yaml
kubectl apply -f k8s/base/secret.example.yaml
kubectl apply -f k8s/base/api-deployment.yaml
kubectl apply -f k8s/base/worker-deployment.yaml
kubectl apply -f k8s/base/go-publisher-deployment.yaml
```

For production, replace `secret.example.yaml` with a sealed secret / external secret manager and pin image tags.
