# Unraid: install AIO step by step

You will create one AIO container in Unraid. This route uses the standard SSD pool **cache** for downloading; the library stays on your regular storage disks.

## Before you begin

- Access to your Unraid server’s web interface.
- A started array with Docker enabled.
- A mounted SSD/NVMe pool named **cache**, with space for downloads. A pool is a group of disks shown under its own name in Unraid.

## 1. Check your server

Open **Main** in Unraid. Confirm the array is started, then find the active pool **cache**.

If your pool has another name, or you have no SSD pool, use [Unraid: advanced](UNRAID_ADVANCED.md). Do not guess paths or format drives to follow this guide.

**Check:** the pool is active and the **Docker** tab exists. If Docker is missing, check **Settings → Docker → Enable Docker**.

## 2. Open Unraid’s terminal

Choose the **>_** terminal icon in the top bar. This command window is already on the server; you do not need an SSH connection from your laptop. Paste the following and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/unraid/install.sh | sh
```

It prepares folders and the AIO template, not separate Sonarr/download containers.

**Check:** the output says **Unraid template ready**. An error about existing downloads means stop and use the advanced guide before adding storage mappings.

## 3. Add the container

Close the terminal and open **Docker → Add Container**. In **Template**, select **my-aio-media-manager** or **aio-media-manager**.

Keep the generated paths. Keep **PUID = 99** and **PGID = 100**, the default user/group for this setup. Set **TZ** to your timezone, for example Europe/Amsterdam. Choose **Apply** and wait for the download.

**Check:** one container named **aio-media-manager** appears with a started/running status.

## 4. Check the download storage

Open **Shares → aio-download-cache**. Its **Primary storage** should be **cache** and **Secondary storage** should be **None**. Older Unraid calls this **Use cache pool: Only**.

Leave it alone if correct. The SSD holds downloading/unpacking work; the library and finished torrents stay on the array.

**Check:** Mover will not move this working share onto the array.

## 5. Open AIO

Click the AIO container icon and choose **WebUI**, or open **http://SERVER-IP:8080** with your actual Unraid IP.

**Check:** the AIO account-creation screen appears. Create the administrator account and pick apps in the wizard. Do not install those same apps separately through Unraid Apps.

After installation: [learn the dashboard](../docs/USAGE.md).

## 6. Copy your first film

If you already have a private file-sharing account on Unraid, use it. Otherwise create a normal user under **Users → Add User**, with a password; do not use root for file sharing.

1. Open **Shares → aio-media-manager → SMB Security Settings**. Set Export to Yes and Security to Private, then grant your file-sharing user read/write access. Leave other users without access unless you intend to share with them.
2. In Windows File Explorer enter `\\SERVER-IP\aio-media-manager`. On macOS use Finder → Go → Connect to Server with `smb://SERVER-IP/aio-media-manager`. Replace SERVER-IP with your Unraid IP.
3. Sign in with your file-sharing user, open media → movies and copy one film you own.

**Check:** the file is in media/movies on the server. Continue with [your first playback](../docs/USAGE.md#first-media).

## If something goes wrong

| What you see | What to do |
|---|---|
| The template is missing | Check that preparation finished with Unraid template ready, then refresh the Docker tab. |
| The pool is absent or has another name | Use the advanced guide for another pool or HDD-only storage. The default command stops on purpose. |
| AIO does not open | Check container status and server IP. For a port conflict, follow the advanced guide. |

## Advanced

For custom storage, SSD options, existing installations and technical settings: [UNRAID — Advanced](UNRAID_ADVANCED.md).

[Official product help: Unraid](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/).
