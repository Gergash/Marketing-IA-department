# Kubernetes manifests

Base común para API + Celery worker (cola default) + video-worker (cola `video_render`)
+ Go publisher. Los entornos se diferencian con overlays kustomize en `k8s/overlays/`.

> El **video-worker es obligatorio** para `content_format=reel` y `user_clip_reel`: sin él
> los renders quedan encolados indefinidamente porque nadie consume `video_render`.

## Renderizar (sin aplicar)
```bash
kubectl kustomize k8s/overlays/dev
kubectl kustomize k8s/overlays/staging
kubectl kustomize k8s/overlays/prod
```

## Aplicar directo (dev local)
```bash
kubectl apply -k k8s/overlays/dev
```

## Vía Skaffold (recomendado)
```bash
# Construye las 3 imágenes y despliega el overlay dev
skaffold run --profile=dev --default-repo=REGION-docker.pkg.dev/PROJECT_ID/REPO
```

## Diferencias por entorno

| Overlay | api | worker | video-worker | APP_ENV | SHOTSTACK_ENV |
|---------|-----|--------|--------------|---------|---------------|
| dev     | 1   | 1      | 1            | dev     | stage         |
| staging | 1   | 1      | 1            | staging | stage         |
| prod    | 3   | 2      | 1            | prod    | v1            |

`video-worker` queda en 1 réplica incluso en prod: cada render de Shotstack cuesta dinero
real y paralelizar no acelera un render individual.

## Secretos

`secret.example.yaml` y `overlays/dev/secret.dev.yaml` son **solo para desarrollo local**
y llevan placeholders. En staging/prod los secretos se inyectan por Secret Manager /
External Secrets — nunca desde el repo.
