<!-- README.md -->
# OfflineDrop

Send photos, videos and files **both ways** between your phone and your computer over your own
Wi-Fi or hotspot. **No internet, no cables, no accounts, no cloud.** Free and open source.

## Download

| Your computer | Download |
| --- | --- |
| **Windows** | [Download OfflineDrop-Windows.exe](https://github.com/Modred14/phone-to-laptop/releases/download/latest/OfflineDrop-Windows.exe) |
| **Mac** (Apple Silicon: M1 or newer) | [Download OfflineDrop-Mac.zip](https://github.com/Modred14/phone-to-laptop/releases/download/latest/OfflineDrop-Mac.zip) |

You only need the internet to download the app. After that, it works with no internet at all.
You can also pass the downloaded file to a friend by USB drive, Bluetooth or AirDrop.

## How to use it (no coding needed)

1. Download the app above and open it. (Mac: unzip it first.)
2. Connect your phone and computer to the **same Wi-Fi**, or turn on your phone's **Personal Hotspot** and connect the computer to it. Internet is not required.
3. A black window appears and your browser opens the laptop page automatically. The black window shows a **QR code** and an address for your phone, like `http://192.168.1.23:8000`.

### Phone to computer

1. On your phone, scan the QR code with the camera (or type the address into the browser).
2. Under **Send to laptop**, tap **Choose files**, then **Send**.
3. The files are saved in your computer's **Downloads** folder.

### Computer to phone

1. On the computer, open `http://localhost:8000` (it opens by itself when the app starts).
2. Under **Send to phone**, click **Choose files**, then **Send**.
3. On your phone, open the same page as above. The files appear under **Files from laptop**. Tap **Download**.

You can also drop files straight into the **OfflineDrop-Share** folder in your home folder, and they will show up on the phone.
To remove a file from the phone's list, click **Stop sharing** on the computer page.

To stop the app, close the black window (or press Ctrl+C).

## If you see a warning

The app is free and not signed with a paid certificate, so your computer may warn you.

- **Windows:** "Windows protected your PC" -> click **More info** -> **Run anyway**. When asked about network access, click **Allow**. Without this the phone cannot connect.
- **Mac:** right-click the app -> **Open** -> **Open**. If it still won't open, go to System Settings -> Privacy & Security -> **Open Anyway**. If it opens as a file, open Terminal, then drag the app into it and press Enter.

## Safety

While the app is open, anyone on the same network can send files to your computer and download the files you are sharing. Use it on your home Wi-Fi or your own hotspot, not on public Wi-Fi, and close it when you are done. Only the computer itself (not other devices) can add or remove shared files.

## For developers

Needs only Python 3, no packages:

```
python3 server.py                            # port 8000
python3 server.py 9000                       # custom port
python3 server.py 8000 /recv/dir /share/dir  # custom port, receive folder, share folder
```

Defaults: received files go to `~/Downloads`, shared files are read from `~/OfflineDrop-Share`.

The apps on the Releases page are rebuilt automatically by GitHub Actions on every push to `main` (see `.github/workflows/build.yml`).

## Website analytics and the /admin dashboard

The landing page (`index.html`) is deployed on Netlify. It counts visits and clicks on the download buttons anonymously, and a private dashboard at `/admin` shows the numbers: unique visitors, download clicks, who is active right now, daily / weekly / monthly stats and a usage chart. The desktop app (`server.py`) is **not** involved and never contacts the internet.

What is stored in Neon Postgres: a random ID the browser makes for itself, the UTC day it visited, and a click on the Windows or Mac button. No IP addresses, user agents, file names or file contents. Visitors who send Do Not Track or Global Privacy Control are skipped. "Download clicks" are clicks, not confirmed downloads.

Setup (Netlify site settings, Environment variables):

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Your Neon connection string (the Netlify Neon extension's `NETLIFY_DATABASE_URL` also works) |
| `ADMIN_PASSWORD` | Your admin password, at least 12 characters |
| `ADMIN_SESSION_SECRET` | A long random string, at least 32 characters (for example `openssl rand -hex 32`) |

Tables are created automatically on first use; `db/schema.sql` is the same schema if you prefer to run it by hand. If either admin variable is missing the dashboard stays disabled. Wrong passwords are rate limited (5 per 15 minutes per IP) and sessions last 8 hours.

## License

MIT. Free to use, copy and modify.