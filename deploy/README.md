# Deployment

The AIO manager is **one process tree / one container**. Never add a Compose service per application.

| Mode | Files |
|------|--------|
| A — Docker | [`Dockerfile`](../Dockerfile), [`docker-compose.yml`](../docker-compose.yml) |
| B — Native Linux / LXC | [`aio-media-manager.service`](aio-media-manager.service) |
| C — NAS templates | [`unraid.xml`](unraid.xml), [`SYNOLOGY.md`](SYNOLOGY.md), [`TRUENAS.md`](TRUENAS.md) |

```bash
docker compose up -d --build
```

Then open `http://localhost:8080`.
