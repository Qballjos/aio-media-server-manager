# Docker on Linux: install AIO step by step

Use this route on a **Linux server with working Docker**. If you have Unraid, Synology or TrueNAS, follow [that platform](README.md) instead; do not run both installations.

## Before you begin

- A Linux server with Docker, Docker Compose and Git. If missing, [install Docker](https://docs.docker.com/engine/install/) first.
- An account already allowed to run Docker commands.
- A computer on the same network to open the dashboard.

## 1. Open a command window on the server

On the server itself, open Terminal. From another computer, open Terminal on macOS or Windows Terminal on Windows and connect with `ssh YOUR-USER@SERVER-IP`, replacing both parts. The blocks below run on the server after that connection.

```bash
docker info
docker compose version
git --version
```

**Check:** Docker prints server information, and Compose/Git print versions. Command not found or permission denied means finish installing/accessing those tools first.

## 2. Download the AIO files

Paste this into the same terminal:

Already have a folder named aio-media-server-manager here? Do not run this block; keep it and use [Advanced](DOCKER_ADVANCED.md). Each line below only runs if the preceding line succeeded.

```bash
git clone https://github.com/Qballjos/aio-media-server-manager.git &&
cd aio-media-server-manager &&
export AMM_DATA_HOST="${HOME}/aio-media-manager" &&
mkdir -p config/vpn backups "${AMM_DATA_HOST}/downloads" "${AMM_DATA_HOST}/media" &&
sed -i -e "s/PUID: \"1000\"/PUID: \"$(id -u)\"/" -e "s/PGID: \"1000\"/PGID: \"$(id -g)\"/" docker-compose.yml
```

This downloads the project, creates its folders and sets AIO’s user to your current Linux account automatically. You do not need to look up numeric IDs or edit a file for this step.

**Check:** there are no errors and you are in aio-media-server-manager, containing docker-compose.yml. Keep this project folder: config holds settings and backups holds saved configuration copies. Media lives separately under aio-media-manager in your home folder. If the project already exists, do not delete it; use the advanced guide.

## 3. Start AIO

In the same project folder, run:

```bash
docker compose pull
docker compose up -d
docker compose ps
```

The first command downloads the software and can take minutes; the second starts it in the background; the third shows its state.

**Check:** one aio-media-manager container shows Up or Running. Closing the terminal afterward does not stop it.

## 4. Open the dashboard

Open **http://SERVER-IP:8080** using your Linux server’s real IP, for example http://192.168.1.50:8080 if that is your server.

**Check:** create the AIO administrator account and select needed apps in the wizard. Install those apps inside AIO, not as additional Docker containers.

After installation: [learn the dashboard](../docs/USAGE.md).

## If something goes wrong

| What you see | What to do |
|---|---|
| Docker permission error | Return to your server’s Docker installation/access setup. Do not randomly switch every command to root. |
| Project folder already exists | Stop, keep it, and follow the advanced existing-install instructions. |
| AIO will not start | Run docker compose logs --tail=100 in the project folder and keep the error. Port conflict? See Advanced. |
| Browser cannot connect | Check docker compose ps, server IP and :8080. Use the same home network. |

## Advanced

For custom storage, SSD options, existing installations and technical settings: [DOCKER — Advanced](DOCKER_ADVANCED.md).
