# TrueNAS SCALE

Use a **single** custom app / Docker deployment. Do not deploy the *Arr stack as separate SCALE apps if you want this appliance model.

## Suggested setup

1. Create datasets, for example:
   - `tank/apps/aio-media-manager`
   - `tank/media`
   - `tank/downloads`
2. Launch one container from the `aio-media-manager` image.
3. Mount:
   - config dataset → `/config`
   - media dataset → `/media`
   - downloads dataset → `/downloads`
4. Publish port `8080`.
5. Set `PUID`/`PGID` to the dataset owner.
6. If the host has an iGPU/NVIDIA GPU, pass `/dev/dri` (and NVIDIA devices when applicable).

The manager UI is `http://<truenas-ip>:8080`.
