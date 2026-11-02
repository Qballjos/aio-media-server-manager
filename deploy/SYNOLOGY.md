# Synology: install AIO step by step

This route is for a **new installation**. You will create one Container Manager project. You do not need to write a configuration file or install each media app separately.

## Before you begin

- A Synology NAS that offers **Container Manager** in Package Center.
- Your own DSM username and password, with administrator rights. Do not assume the example account admin exists.
- A computer on the same home network. Keep DSM open in your browser.

## 1. Install Container Manager

In DSM, open **Package Center**, find **Container Manager**, install it and open it. Let DSM finish setting it up.

**Check:** File Station now has a shared folder named **docker**. Do not create it yourself before installing the package. This route uses docker on volume1; if yours is elsewhere, use the [advanced Synology guide](SYNOLOGY_ADVANCED.md).

## 2. Enable your personal folder and SSH

Open **Control Panel → User & Group → Advanced** and enable **User Home Service**. This gives your DSM account a personal folder for downloads and media.

Then open **Control Panel → Terminal & SNMP → Terminal**, enable **SSH service**, leave port **22** and choose **Apply**.

**Check:** File Station shows **home**, and SSH is enabled.

## 3. Connect from your computer

Open **Terminal** on macOS or **Windows Terminal / PowerShell** on Windows. Type `ssh YOUR-USERNAME@NAS-IP`, replacing both parts. For a user alex and a NAS at 192.168.1.50, the example is:

```bash
ssh alex@192.168.1.50
```

Use your own details, not the example address. Find the NAS IP in DSM’s browser address or **Control Panel → Network → Network Interface**. Accept the first connection only if the address is correct, then enter your DSM password. No characters appear while typing a password; this is normal.

**Check:** the prompt now identifies your NAS. The following command runs on that NAS, not your laptop.

## 4. Prepare the AIO project

Paste this complete block into the connected terminal and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Qballjos/aio-media-server-manager/main/deploy/synology/install.sh | sudo sh
```

It downloads the preparation script and creates the folders and project file. It does not start AIO yet. If sudo asks for a password, use your DSM password.

**Check:** the last message says **Container Manager project files are ready**. Note the **Compose** file and project folder printed there. Do not continue if the script reports an error.

## 5. Create the project in DSM

Return to **Container Manager → Project → Create**.

1. Name: **aio-media-manager**.
2. Path: select the project folder printed by the script; normally **docker → aio-media-manager**.
3. Use the **existing docker-compose.yml** there. If your DSM asks for an upload, select that generated file instead of creating a different configuration.
4. Keep the generated settings, finish and start the project.

**Check:** one container named aio-media-manager becomes active. The first download may take several minutes.

## 6. Open your dashboard

Open **http://NAS-IP:8080**, using your own NAS address. The example NAS would use http://192.168.1.50:8080.

**Check:** AIO asks you to create an administrator account. Create it and complete the wizard; choose only the apps you need. Your files are normally under **File Station → home → aio-media-manager**.

Finish the SSH connection with `exit`. Disabling SSH in DSM afterward does not stop AIO.

After installation: [learn the dashboard](../docs/USAGE.md).

## If something goes wrong

| What you see | What to do |
|---|---|
| Container Manager is unavailable | Check whether Synology supports it on your model. A manually created docker folder is not a substitute. |
| Permission denied or script error | Check your DSM account, running Container Manager and existing docker folder. Keep the exact error message. |
| The browser cannot open AIO | Check that the project is active. Use the NAS IP, not your laptop IP, followed by :8080. |

## Advanced

For custom storage, SSD options, existing installations and technical settings: [SYNOLOGY — Advanced](SYNOLOGY_ADVANCED.md).

[Official product help: Synology](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project?version=7).
