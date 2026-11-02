# Using AIO, step by step

Start here once you can open AIO in your browser. First get one app working; add more when you need them.

## 1. Finish your first setup

Create the administrator account, then complete the wizard. For a small start, choose Jellyfin to play media you already own. Leave VPN and access from outside your home off until everything works locally. Wait until the chosen app says Running in Catalog.

## 2. Know the three pages

| AIO | |
|---|---|
| Home | See downloads, upcoming releases and server information. You can arrange the widgets yourself. |
| Catalog | Install apps, see whether they are running and choose Open to open an app. |
| Settings | Change AIO’s appearance, account and updates. This is not where you add films to a media server. |

## Using the new catalog {#catalog-menu}

Open **Catalog** at the top. The left sidebar helps you choose what to see; the apps appear on the right.

| Sidebar option | What you see |
|---|---|
| **Discover** | Featured apps and the complete catalog. |
| **My apps** | Apps you have already installed, including stopped apps. |
| **Active** | Only apps that are running. |
| **Available** | Apps you can install. |
| **Search / Category** | Find an app by name or choose a type of app. |

Use the sort control above the app list for Popularity or A to Z. Missing an app? Clear the search and choose Discover to remove the status/category selection.

To start with Jellyfin: search for Jellyfin. Choose **Install** if it is not installed, wait for **Running**, then choose **Open**. If it is installed but stopped, choose **Start** first. Open launches Jellyfin in its own browser tab.

Click an app’s name, icon or row to open its **app settings popup**. This does not open the app itself. The **⋯** button offers Settings, Stop, Restart, Logs, Update and Uninstall as applicable. Close the popup with × or Escape. Only save changes when you intend to change that app.

**Catalog app settings** change one app. The **Settings** page in the top navigation changes AIO itself: profile, appearance, connections, backups and updates.

![Catalog: sidebar, app rows and Open buttons](screenshots/light/catalog.png?v=app-store-20261102)

## Find your way around Settings {#settings-menu}

The settings page uses the same sidebar-and-content layout as the catalog. On a computer, choose a group and page on the left; the selected page appears on the right. The search field filters the menu, not the values of your settings. Scroll the sidebar to find lower groups. On a phone, open **Settings sections** and choose a page.

| What do you want to change? | Choose this page |
|---|---|
| Name, profile photo or password | Personal → **Profile** |
| Language, theme or wallpaper | Personal → **Language and appearance** |
| App dock or sign-in message | Dashboard → **Start page** |
| Update an app | Maintenance → **Updates** |
| Make a settings backup | Maintenance → **Backups** |
| Find why a widget is empty | System → **Help and diagnostics** |
| API keys, TV or Homey connections | Connections → **App connections** |

The sidebar only selects a page. Change a setting on the right and use that section’s **Save** button when shown. Arrange widgets directly on **Home**, using the four-block layout button; Start page settings control the dock and sign-in text.

![Settings: grouped sidebar and search](screenshots/light/settings.png?v=app-store-20261102)

## 3. Open your first app

Choose Catalog, find Jellyfin and choose Open. Complete Jellyfin’s own setup if requested. When it asks for library folders, use /data/media/movies for films and /data/media/tv for shows with the default installation. Those names refer to the media folders already connected by your platform guide. Do not create another copy because your NAS shows a different folder path.

**Check: Jellyfin opens in its own browser tab. A folder without media will look empty; that is normal.**

## 4. Play your first film {#first-media}

Use a film file you already own, for example MyFilm.mp4. Copy it into the **movies folder on your server**, not into the Downloads folder and not into the website demo.

| Server | Where to copy the file |
|---|---|
| Synology | In DSM File Station: home → aio-media-manager → media → movies. Choose Upload and select the file from your computer. |
| Unraid | Open the aio-media-manager network share, then media → movies. The last step of the Unraid guide explains enabling that private share. |
| TrueNAS | Open the aio-media network share, then media → movies. Step 7 in the TrueNAS guide sets up access. |
| Docker on Linux | On the server, open your home folder → aio-media-manager → media → movies. From another computer you can copy over SSH with scp as shown below. |

For a remote Linux server: run this **on your computer**, replacing the file path, username and server IP. The example copies to the standard home-folder installation.

On Windows a file path may look like `C:\Users\Alex\Videos\MyFilm.mp4`; on macOS it may look like `/Users/alex/Movies/MyFilm.mp4`. Keep the quotes around your actual path. Use the same server username and IP that you used for SSH.

```bash
scp "/PATH/TO/YOUR/FILM.mp4" YOUR-USER@SERVER-IP:aio-media-manager/media/movies/
```

For a series, use media/tv instead. After copying, open Jellyfin → Dashboard → Libraries and choose Scan All Libraries (or the scan action for your library). Return to the Jellyfin home screen, open the film and choose Play.

**Check: the film appears and starts playing. If it does not appear, verify the server file is in the same folder you selected in Jellyfin, then scan again.**

## 5. Arrange your Home widgets {#customize-home}

<div class="widget-visual-guide" role="group" aria-label="Arrange your Home widgets">
<div class="widget-visual-step"><span class="visual-number">1</span><strong>The edit button</strong><div class="visual-nav"><span>Home</span><span>Catalog</span><span>Settings</span><span class="visual-highlight"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="7" height="10" rx="1.5"/><rect x="14" y="3" width="7" height="6" rx="1.5"/><rect x="3" y="17" width="7" height="4" rx="1.5"/><rect x="14" y="13" width="7" height="8" rx="1.5"/></svg></span></div><p>On Home, choose the four-block layout icon next to the page tabs. Widget handles and an editing toolbar appear.</p></div>
<div class="widget-visual-step"><span class="visual-number">2</span><strong>Move: drag the grip</strong><div class="visual-widget"><span class="visual-grip">⠿</span><span class="visual-remove">×</span><strong>Downloading</strong><span class="visual-widget-line"></span><span class="visual-widget-line short"></span><span class="visual-corner">↘</span></div><p>Resize: drag this corner</p></div>
<div class="widget-visual-step"><span class="visual-number">3</span><strong>Choose what to add</strong><div class="visual-toolbar"><span>＋ Add widget</span><span>Done</span></div><p>Choose Add widget, pick This size or Every size, then choose a widget. Changes save automatically; choose Done when finished.</p></div>
</div>

[Arrange your Home widgets](index.md#app-preview){ .md-button .md-button--primary }

These pictures explain the real controls. The website example uses sample data; it cannot change your actual dashboard.

### Why is a widget empty?

First check that the related app is running in Catalog. Recently added needs media in Jellyfin/Plex; the calendar needs scheduled titles from your connected apps. An empty widget can disappear outside editing mode. Adding a widget does not install the app it needs.

## 6. What are the other apps for?

| App | |
|---|---|
| Jellyfin / Plex | Play your existing media. |
| Sonarr / Radarr | Organise shows / films and automate downloads you choose. |
| SABnzbd / NZBGet | Download from Usenet; this needs your own provider account. |
| qBittorrent | Download and seed torrents. |
| Prowlarr | Manage the search sources used by the automation apps. |

You do not need all of them. Add an app from Catalog only when you know what you want it to do. The detailed connection steps are under Advanced.

## 7. Keep apps up to date

Use Settings → Updates for the apps inside AIO. Updating AIO itself is a separate action in your NAS/Docker interface; the platform’s advanced guide explains that. Make a configuration backup in Settings → Backups before changing a working setup.

## Screens and technical reference {#screens}

[Screens and technical reference](USAGE_ADVANCED.md#screens).

## Advanced

For custom connections, VPN, keys and detailed diagnostics, continue with the advanced dashboard guide. [Advanced](USAGE_ADVANCED.md).
