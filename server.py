# server.py
#!/usr/bin/env python3
"""
OfflineDrop: send files between your phone and your laptop over a local
network (Wi-Fi, hotspot, or USB tethering). Works both ways:

  Phone -> Laptop : open the laptop's address on the phone, pick files, Send.
  Laptop -> Phone : open http://localhost:PORT on the laptop, pick files, Send,
                    then download them from the same address on the phone.

No internet needed, no packages to install, just Python 3.

Usage:
    python3 server.py                          # port 8000
    python3 server.py 9000                     # custom port
    python3 server.py 8000 /recv/dir /share/dir

Phone -> Laptop files are saved to ~/Downloads (default).
Laptop -> Phone files are shared from ~/OfflineDrop-Share (default).
You can also just drop files into that share folder by hand.
"""
import functools
import json
import os
import re
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote, quote

# Show every message immediately instead of waiting for the buffer to flush.
print = functools.partial(print, flush=True)

# Windows consoles often can't print every character; never let that crash a transfer.
try:
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
except Exception:
    pass

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
SAVE_DIR = os.path.abspath(
    os.path.expanduser(sys.argv[2] if len(sys.argv) > 2 else "~/Downloads")
)
SHARE_DIR = os.path.abspath(
    os.path.expanduser(sys.argv[3] if len(sys.argv) > 3 else "~/OfflineDrop-Share")
)
CHUNK = 1024 * 1024  # 1 MB

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OfflineDrop</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px; font-family: -apple-system, system-ui, sans-serif;
         background: #111; color: #eee; max-width: 520px; margin-inline: auto; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 17px; margin: 28px 0 10px; padding-top: 18px; border-top: 1px solid #2a2a2a; }
  h2.first { margin-top: 20px; border-top: 0; padding-top: 0; }
  p.sub { color: #999; margin: 0 0 20px; font-size: 14px; }
  label.pick { display: block; text-align: center; padding: 28px 16px; border: 2px dashed #444;
               border-radius: 14px; font-size: 17px; background: #1a1a1a; }
  input[type=file] { display: none; }
  button { width: 100%; margin-top: 14px; padding: 16px; font-size: 17px; font-weight: 600;
           border: 0; border-radius: 12px; background: #2f7df6; color: #fff; }
  button:disabled { background: #333; color: #777; }
  .file { margin-top: 12px; background: #1a1a1a; border-radius: 10px; padding: 10px 12px; font-size: 14px; }
  .file .row { display: flex; justify-content: space-between; gap: 8px; }
  .file .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { height: 6px; background: #333; border-radius: 3px; margin-top: 8px; overflow: hidden; }
  .bar > div { height: 100%; width: 0; background: #2f7df6; transition: width .1s; }
  .done .bar > div { background: #34c759; }
  .err .bar > div { background: #ff453a; }
  .meta { color: #999; font-size: 12px; margin-top: 4px; }
  .empty { color: #777; font-size: 14px; }
  .btn { display: block; width: 100%; margin-top: 10px; padding: 11px; font-size: 15px; font-weight: 600;
         text-align: center; text-decoration: none; border: 0; border-radius: 10px;
         background: #2f7df6; color: #fff; }
  .btn.red { background: #3a2222; color: #ff6b61; }
</style>
</head>
<body>
  <h1 id="title"></h1>
  <p class="sub" id="sub"></p>

  <h2 class="first" id="sendHead"></h2>
  <label class="pick" id="pick">
    Tap to choose files
    <input type="file" id="files" multiple>
  </label>
  <button id="send" disabled>Send</button>
  <div id="list"></div>

  <h2 id="recvHead"></h2>
  <div id="shared"></div>

<script>
const MODE = '__MODE__';
const isLaptop = MODE === 'laptop';

const T = isLaptop ? {
  title: 'OfflineDrop (laptop)',
  sub: 'Send files to your phone. Open the same address on your phone to download them.',
  sendHead: 'Send to phone',
  recvHead: 'Files you are sharing',
  pick: 'Click to choose files',
  empty: 'Nothing shared yet.'
} : {
  title: 'OfflineDrop',
  sub: 'Send files to the laptop, or download files the laptop is sharing.',
  sendHead: 'Send to laptop',
  recvHead: 'Files from laptop',
  pick: 'Tap to choose files',
  empty: 'The laptop is not sharing any files yet.'
};

const input = document.getElementById('files');
const send = document.getElementById('send');
const list = document.getElementById('list');
const pick = document.getElementById('pick');
const shared = document.getElementById('shared');
let queue = [];
let lastJson = null;

document.getElementById('title').textContent = T.title;
document.getElementById('sub').textContent = T.sub;
document.getElementById('sendHead').textContent = T.sendHead;
document.getElementById('recvHead').textContent = T.recvHead;
pick.firstChild.textContent = T.pick;

const fmt = n => n > 1e9 ? (n/1e9).toFixed(2)+' GB' : n > 1e6 ? (n/1e6).toFixed(1)+' MB' : (n/1e3).toFixed(0)+' KB';

input.onchange = () => {
  queue = [...input.files];
  list.innerHTML = '';
  queue.forEach((f, i) => {
    const d = document.createElement('div');
    d.className = 'file'; d.id = 'f' + i;
    d.innerHTML = '<div class="row"><span class="name"></span><span>' + fmt(f.size) + '</span></div>' +
                  '<div class="bar"><div></div></div><div class="meta">Ready</div>';
    d.querySelector('.name').textContent = f.name;
    list.appendChild(d);
  });
  send.disabled = queue.length === 0;
  pick.firstChild.textContent = queue.length ? queue.length + ' file(s) selected. Tap to change' : T.pick;
};

function upload(file, i) {
  return new Promise(resolve => {
    const el = document.getElementById('f' + i);
    const bar = el.querySelector('.bar > div');
    const meta = el.querySelector('.meta');
    const t0 = Date.now();
    const xhr = new XMLHttpRequest();
    xhr.open('POST', (isLaptop ? '/share' : '/upload') + '?name=' + encodeURIComponent(file.name));
    xhr.upload.onprogress = e => {
      if (!e.lengthComputable) return;
      bar.style.width = (e.loaded / e.total * 100) + '%';
      const speed = e.loaded / ((Date.now() - t0) / 1000 || 1);
      meta.textContent = Math.round(e.loaded / e.total * 100) + '%  ·  ' + fmt(speed) + '/s';
    };
    xhr.onload = () => {
      if (xhr.status === 200) { el.classList.add('done'); bar.style.width = '100%'; meta.textContent = 'Sent ✓'; }
      else { el.classList.add('err'); meta.textContent = 'Failed (' + xhr.status + ')'; }
      resolve();
    };
    xhr.onerror = () => { el.classList.add('err'); meta.textContent = 'Connection lost'; resolve(); };
    xhr.send(file);
  });
}

send.onclick = async () => {
  send.disabled = true;
  for (let i = 0; i < queue.length; i++) await upload(queue[i], i);
  send.textContent = 'Send more';
  input.value = ''; queue = [];
  pick.firstChild.textContent = T.pick;
  refresh();
};

async function refresh() {
  try {
    const r = await fetch('/files', { cache: 'no-store' });
    const text = await r.text();
    if (text === lastJson) return;
    lastJson = text;
    const files = JSON.parse(text);
    shared.innerHTML = '';
    if (!files.length) {
      const e = document.createElement('div');
      e.className = 'empty';
      e.textContent = T.empty;
      shared.appendChild(e);
      return;
    }
    files.forEach(f => {
      const d = document.createElement('div');
      d.className = 'file';
      const row = document.createElement('div');
      row.className = 'row';
      const n = document.createElement('span');
      n.className = 'name';
      n.textContent = f.name;
      const s = document.createElement('span');
      s.textContent = fmt(f.size);
      row.appendChild(n); row.appendChild(s);
      d.appendChild(row);
      if (isLaptop) {
        const b = document.createElement('button');
        b.className = 'btn red';
        b.textContent = 'Stop sharing';
        b.onclick = async () => {
          await fetch('/delete?name=' + encodeURIComponent(f.name), { method: 'POST' });
          lastJson = null;
          refresh();
        };
        d.appendChild(b);
      } else {
        const a = document.createElement('a');
        a.className = 'btn';
        a.textContent = 'Download';
        a.href = '/download?name=' + encodeURIComponent(f.name);
        a.setAttribute('download', f.name);
        d.appendChild(a);
      }
      shared.appendChild(d);
    });
  } catch (e) { /* server not reachable right now; try again next time */ }
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


def safe_name(raw: str) -> str:
    name = os.path.basename(unquote(raw).replace("\\", "/")) or "file"
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(". ") or "file"
    return name[:200]


def unique_path(directory: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    path = os.path.join(directory, name)
    n = 1
    while os.path.exists(path):
        path = os.path.join(directory, f"{base} ({n}){ext}")
        n += 1
    return path


def list_shared():
    items = []
    try:
        for entry in os.scandir(SHARE_DIR):
            if (entry.is_file() and not entry.name.endswith(".part")
                    and not entry.name.startswith(".")):
                st = entry.stat()
                items.append({"name": entry.name, "size": st.st_size, "mtime": st.st_mtime})
    except OSError:
        pass
    items.sort(key=lambda i: i["mtime"], reverse=True)
    for i in items:
        del i["mtime"]
    return items


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass  # keep the terminal clean; we print our own lines

    def _is_local(self):
        # True only when the request comes from the laptop itself.
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            mode = "laptop" if self._is_local() else "phone"
            self._reply(200, PAGE.replace("__MODE__", mode).encode(), "text/html; charset=utf-8")
        elif parsed.path == "/files":
            self._reply(200, json.dumps(list_shared()).encode(), "application/json")
        elif parsed.path == "/download":
            self._download(parsed)
        else:
            self._reply(404, b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/upload":
            # Phone -> laptop (anyone on the network may send)
            return self._receive(parsed, SAVE_DIR, "RECEIVING", "RECEIVED")
        if parsed.path in ("/share", "/delete"):
            # Laptop -> phone management: only the laptop itself may do this
            if not self._is_local():
                self.close_connection = True
                return self._reply(403, b"Only the laptop can do this")
            if parsed.path == "/share":
                return self._receive(parsed, SHARE_DIR, "SHARING", "SHARED")
            return self._delete(parsed)
        self.close_connection = True
        self._reply(404, b"Not found")

    def _receive(self, parsed, directory, start_label, done_label):
        name = safe_name(parse_qs(parsed.query).get("name", ["file"])[0])
        try:
            remaining = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.close_connection = True
            return self._reply(400, b"Bad length")

        dest = unique_path(directory, name)
        part = dest + ".part"
        t0 = time.time()
        total = remaining
        print(f"  [{start_label}] {name}  {total/1e6:.1f} MB")
        try:
            with open(part, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK, remaining))
                    if not chunk:
                        raise ConnectionError("client disconnected")
                    f.write(chunk)
                    remaining -= len(chunk)
            os.replace(part, dest)
        except Exception as e:
            try:
                os.remove(part)
            except OSError:
                pass
            print(f"  [FAILED] {name}: {e}")
            self.close_connection = True
            return

        secs = max(time.time() - t0, 0.001)
        self._reply(200, b"ok")
        print(f"  [{done_label}] {os.path.basename(dest)}  {total/1e6:.1f} MB  ({total/1e6/secs:.1f} MB/s)")

    def _delete(self, parsed):
        name = os.path.basename(parse_qs(parsed.query).get("name", [""])[0])
        path = os.path.join(SHARE_DIR, name)
        if name and os.path.isfile(path):
            try:
                os.remove(path)
                print(f"  [UNSHARED] {name}")
                return self._reply(200, b"ok")
            except OSError as e:
                print(f"  [FAILED] could not remove {name}: {e}")
                return self._reply(500, b"Could not remove")
        self._reply(404, b"File not found")

    def _download(self, parsed):
        name = os.path.basename(parse_qs(parsed.query).get("name", [""])[0])
        path = os.path.join(SHARE_DIR, name)
        if not name or name.endswith(".part") or not os.path.isfile(path):
            return self._reply(404, b"File not found")

        size = os.path.getsize(path)
        ascii_name = name.encode("ascii", "replace").decode().replace('"', "_")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        t0 = time.time()
        print(f"  [SENDING] {name}  {size/1e6:.1f} MB")
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except OSError as e:
            print(f"  [FAILED] {name}: {e}")
            self.close_connection = True
            return
        secs = max(time.time() - t0, 0.001)
        print(f"  [SENT] {name}  {size/1e6:.1f} MB  ({size/1e6/secs:.1f} MB/s)")


def local_ips():
    ips = []
    # Trick: no packets are sent, it just asks the OS which interface would be used.
    for target in ("10.255.255.255", "172.20.10.1", "192.168.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
        except OSError:
            pass
    return ips


def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    os.makedirs(SHARE_DIR, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ips = local_ips()

    print("\n  OfflineDrop is running")
    print(f"  Phone -> laptop files are saved to: {SAVE_DIR}")
    print(f"  Laptop -> phone files are shared from: {SHARE_DIR}\n")
    print("  On THIS laptop, open this to send files to your phone:")
    print(f"    http://localhost:{PORT}\n")
    if ips:
        print("  On your PHONE, open Safari/Chrome and go to:")
        for ip in ips:
            print(f"    http://{ip}:{PORT}")
    else:
        print("  Couldn't detect an IP. Connect both devices to the same network,")
        print(f"  find the laptop's IP address, and open http://<that-ip>:{PORT} on the phone.")
    print("\n  Press Ctrl+C to stop.\n")

    # Open the laptop page automatically (harmless if it fails).
    try:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()