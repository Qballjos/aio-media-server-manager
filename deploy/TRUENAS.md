# TrueNAS: install AIO step by step

Use the **Custom App form** in TrueNAS SCALE 24.10 or newer. This starter route runs AIO and Jellyfin; additional apps and their ports can be added later.

## Before you begin

- Access to the TrueNAS interface with app/storage administration rights.
- An existing storage pool; do not create or format one just to follow this guide.
- Apps storage already configured. If TrueNAS first asks you to select an Apps pool, complete that setup.

## 1. Create three AIO storage folders

Open **Datasets**, select your existing pool and use **Add Dataset** to create aio-config, aio-data and aio-backups beneath it. A dataset is a storage folder managed by TrueNAS.

Note each full path displayed. For a pool named media, examples are /mnt/media/aio-config, /mnt/media/aio-data and /mnt/media/aio-backups. Use your own pool name, not the example.

**Check:** three new datasets exist. Do not choose an existing folder containing other data for these steps.

## 2. Record the app account

Open **Credentials → Local Users / Users**, find apps and note its numeric user ID and group ID. Both are often 568, but use the values your system shows. These numbers identify which app account needs folder access; they are not your login password.

**Check:** you have noted two numbers. The folder access is applied in the app form below; do not change permissions on your whole pool.

## 3. Open the Custom App form

Open **Apps → Discover Apps → Custom App**. Choose the regular form, not Install via YAML. Labels vary by version.

| Field | Value |
|---|---|
| Application name | aio-media-manager |
| Image repository | ghcr.io/qballjos/aio-media-server-manager |
| Image tag | latest |

**Check:** repository and tag are in the correct fields; do not append :latest again if there is a separate tag field.

## 4. Connect the folders

Under **Storage → Host Path**, add these three mappings. On the left select the real NAS dataset; on the right enter AIO’s folder name:

| NAS folder | Mount path in AIO |
|---|---|
| Your aio-config path | /config |
| Your aio-data path | /data |
| Your aio-backups path | /backups |

Keep each mapping writable. For each of the three **Host Path** mappings, select **Enable ACL**, choose **Add** under ACL Entries, set **ID Type = User**, enter the apps user ID you recorded in **ID**, and set **Access = Full Control**. Apply this only to the three new AIO datasets. ACL means the list of accounts allowed to use a folder. If your form lacks these controls, use the TrueNAS instructions for your version before installing.

**Check:** three different NAS paths map to exactly /config, /data and /backups.

## 5. Enter the basic settings

Add **Environment variables**:

| Name | Value |
|---|---|
| PUID | Your recorded apps user number |
| PGID | Your recorded apps group number |
| AMM_DOWNLOAD_DIR | /data/downloads |
| AMM_MEDIA_DIR | /data/media |

Under **Port forwarding**, add TCP **8080 to 8080** for AIO and **8096 to 8096** for Jellyfin. Leave VPN, GPU and optional extras off for now.

**Check:** two port mappings exist. If a port is occupied, stop and read Advanced rather than choosing random numbers.

## 6. Install and open AIO

Choose **Install** and wait for Running. Open **http://TRUENAS-IP:8080** yourself with the actual server IP; a WebUI button is not present in every version/install method.

**Check:** create the AIO administrator account. Select only Jellyfin at first, then open it from AIO Catalog. Add more apps later with their ports from the advanced reference.

After installation: [learn the dashboard](../docs/USAGE.md).

## 7. Make the media folder accessible from your computer

To copy your first film, you need file access as well as the AIO app. Use a normal TrueNAS file-sharing account, not root or apps. If you do not have one, create it under **Credentials → Users → Add**, set its password and enable its SMB/file-sharing authentication.

1. Open **Datasets → aio-data → Permissions → Edit ACL**. Add your file-sharing user with **Modify** access and inheritance to files/subfolders. Keep the existing apps access; do not replace the whole list. When saving, select **Apply permissions recursively** so existing subfolders receive this access too. Apply this only to aio-data.
2. Under **Shares → Windows (SMB) Shares → Add**, choose the real aio-data dataset path. Name the share **aio-media** and save. Start the SMB service if TrueNAS prompts you.
3. On Windows, enter `\\TRUENAS-IP\aio-media` in **File Explorer**, not your browser. On macOS use **Finder → Go → Connect to Server** and `smb://TRUENAS-IP/aio-media`. Replace the IP and sign in with the file-sharing account.
4. Open media → movies and copy one film you own into it. The AIO app creates these subfolders when it starts. Leave config and backups out of this share.

**Check:** the film is visible in the NAS folder. Continue with [your first playback](../docs/USAGE.md#first-media).


## If something goes wrong

| What you see | What to do |
|---|---|
| The form looks different | Check your TrueNAS version. This route uses Docker-based Apps from 24.10 onward; consult official TrueNAS help or Advanced. |
| Permission denied | Check the three AIO datasets and apps user; do not change the whole pool. |
| AIO runs but cannot be opened | Use the TrueNAS IP with :8080 and check the port mapping. |
| Another app cannot be opened | This starter publishes only AIO/Jellyfin. Add the extra app’s port using Advanced. |

## Advanced

For custom storage, SSD options, existing installations and technical settings: [TRUENAS — Advanced](TRUENAS_ADVANCED.md).

[Official product help: TrueNAS](https://www.truenas.com/docs/scale/25.04/scaleuireference/apps/installcustomappscreens/).

[TrueNAS: app storage and folder access](https://apps.truenas.com/getting-started/app-storage/).
