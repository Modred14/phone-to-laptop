<!-- README.md -->
# OfflineDrop

Send photos, videos and files **both ways** between your phone and your computer over your own
Wi-Fi or hotspot. **No internet, no cables, no accounts, no cloud.** Free and open source.

## How to use it (no coding needed)

1. Go to the **Releases** page of this project and download the file for your computer:
   - **Windows:** `OfflineDrop-Windows.exe`
   - **Mac:** `OfflineDrop-Mac.zip` (unzip it first)
2. Connect your phone and computer to the **same Wi-Fi**, or turn on your phone's **Personal Hotspot** and connect the computer to it. Internet is not required.
3. Open the app. A black window appears, and your browser opens the laptop page automatically. The black window also shows an address for your phone, like `http://192.168.1.23:8000`.

### Phone to computer

1. On your phone, open the browser and type the address from the black window.
2. Under **Send to laptop**, tap **Choose files**, then **Send**.
3. The files are saved in your computer's **Downloads** folder.

### Computer to phone

1. On the computer, open `http://localhost:8000` (it opens by itself when the app starts).
2. Under **Send to phone**, click **Choose files**, then **Send**.
3. On your phone, open the same address as above. The files appear under **Files from laptop**. Tap **Download**.

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

Releases are built automatically with GitHub Actions when a version tag (like `v1.0.0`) is pushed.

## License

MIT. Free to use, copy and modify.