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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>OfflineDrop</title>
<style>
  :root {
    --bg: #e8edf4; --ink: #101828; --mut: #475467; --tile: rgba(255,255,255,.45);
    --glass: rgba(255,255,255,.52); --edge: rgba(255,255,255,.85); --line: rgba(16,24,40,.14);
    --shadow: 0 12px 40px rgba(16,24,40,.10);
    --btn: #101828; --btn-ink: #ffffff; --danger: #d92d20; --danger-bg: rgba(255,93,93,.16);
    --blue: #2f5bff; --mint: #35d0a8; --sun: #ff9f43; --lilac: #b39bff;
    color-scheme: light dark;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0b1020; --ink: #eef2ff; --mut: #a8b2c9; --tile: rgba(255,255,255,.07);
      --glass: rgba(255,255,255,.08); --edge: rgba(255,255,255,.18); --line: rgba(255,255,255,.18);
      --shadow: 0 12px 40px rgba(0,0,0,.45);
      --btn: #eef2ff; --btn-ink: #0b1020; --danger: #ff8a80; --danger-bg: rgba(255,93,93,.18);
    }
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin: 0; padding: 20px 16px 40px; min-height: 100vh; background: var(--bg); color: var(--ink);
         font: 400 16px/1.5 -apple-system, "Segoe UI", system-ui, Roboto, sans-serif; overflow-x: hidden; }
  main { max-width: 540px; margin: 0 auto; display: grid; gap: 16px; }

  /* Solid shapes behind the glass, so the blur has something to bend */
  .shapes { position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; }
  .shapes i { position: absolute; display: block; }
  .s1 { width: 340px; height: 340px; border-radius: 50%; background: var(--blue); right: -110px; top: 40px; }
  .s2 { width: 160px; height: 160px; border-radius: 50%; background: var(--sun); left: -40px; top: 52%; }
  .s3 { width: 230px; height: 230px; border-radius: 52px; background: var(--mint); right: -40px; bottom: -70px; transform: rotate(18deg); }
  .s4 { width: 96px; height: 96px; border-radius: 50%; background: var(--lilac); left: 34%; top: 6px; }

  .glass {
    background: var(--glass);
    -webkit-backdrop-filter: blur(24px) saturate(165%);
    backdrop-filter: blur(24px) saturate(165%);
    border: 1px solid var(--edge);
    box-shadow: var(--shadow), inset 0 1px 0 var(--edge);
  }

  .hero { display: flex; align-items: center; gap: 14px; padding: 18px 20px; border-radius: 26px; }
  .mark { flex: none; width: 46px; height: 46px; border-radius: 14px; background: var(--blue); display: grid; place-items: center; }
  h1 { font-size: 22px; font-weight: 750; letter-spacing: -.02em; line-height: 1.15; margin: 0 0 3px; }
  p.sub { color: var(--mut); margin: 0; font-size: 14px; line-height: 1.4; }

  .card { padding: 20px; border-radius: 28px; }
  h2 { font-size: 17px; font-weight: 700; letter-spacing: -.01em; margin: 0 0 14px; }

  label.pick { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; padding: 26px 16px;
               border: 1.5px dashed var(--line); border-radius: 20px; background: var(--tile); font-size: 16px; font-weight: 600; cursor: pointer; }
  label.pick::before { content: "+"; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
                       background: var(--btn); color: var(--btn-ink); font-size: 24px; font-weight: 400; line-height: 1; }
  label.pick:hover, label.pick:focus-within { border-color: var(--blue); }
  input[type=file] { display: none; }

  button { width: 100%; margin-top: 14px; padding: 15px; font-family: inherit; font-size: 16px; font-weight: 600;
           border: 0; border-radius: 999px; background: var(--btn); color: var(--btn-ink); cursor: pointer; }
  button:disabled { background: var(--line); color: var(--mut); cursor: default; }
  button:focus-visible, a:focus-visible { outline: 3px solid var(--blue); outline-offset: 3px; }

  .file { margin-top: 12px; background: var(--tile); border: 1px solid var(--edge); border-radius: 16px; padding: 12px 14px; font-size: 14px; }
  .file .row { display: flex; justify-content: space-between; gap: 10px; }
  .file .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .file .row span:last-child { color: var(--mut); flex: none; }
  .bar { height: 7px; background: var(--line); border-radius: 99px; margin-top: 9px; overflow: hidden; }
  .bar > div { height: 100%; width: 0; background: var(--blue); border-radius: 99px; transition: width .1s; }
  .done .bar > div { background: var(--mint); }
  .err .bar > div { background: #ff5d5d; }
  .meta { color: var(--mut); font-size: 12px; margin-top: 5px; }
  .empty { color: var(--mut); font-size: 14px; padding: 6px 2px; }

  .btn { display: block; width: 100%; margin-top: 10px; padding: 11px; font-size: 15px; text-align: center; text-decoration: none;
         border-radius: 999px; background: var(--btn); color: var(--btn-ink); font-weight: 600; }
  .btn.red { background: var(--danger-bg); color: var(--danger); }

  .foot { text-align: center; color: var(--mut); font-size: 13px; margin: 4px 0 0; }
</style>
</head>
<body>
<div class="shapes" aria-hidden="true"><i class="s1"></i><i class="s2"></i><i class="s3"></i><i class="s4"></i></div>
<main>
  <header class="glass hero">
    <span class="mark" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 8h14l-4-4M19 16H5l4 4"/></svg></span>
    <div>
      <h1 id="title"></h1>
      <p class="sub" id="sub"></p>
    </div>
  </header>

  <section class="glass card">
    <h2 id="sendHead"></h2>
    <label class="pick" id="pick">
      Tap to choose files
      <input type="file" id="files" multiple>
    </label>
    <button id="send" disabled>Send</button>
    <div id="list"></div>
  </section>

  <section class="glass card">
    <h2 id="recvHead"></h2>
    <div id="shared"></div>
  </section>

  <p class="foot">Files stay on your local network. Nothing goes through the internet.</p>
</main>

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


# ---------------------------------------------------------------------------
# Tiny QR code generator (byte mode, error correction level M, versions 1-6),
# so the startup window can show a code the phone camera can scan.
# The structure follows Project Nayuki's MIT-licensed QR Code generator.
# ---------------------------------------------------------------------------
_QR_ECC_PER_BLOCK = [10, 16, 26, 18, 24, 16]  # level M, versions 1..6
_QR_NUM_BLOCKS = [1, 1, 1, 2, 2, 4]


def _gf_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 2)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def make_qr(text):
    """Return the QR code for `text` as a list of rows of booleans (True = dark)."""
    data = text.encode("utf-8")
    for ver in range(1, 7):
        raw = (16 * ver + 128) * ver + 64
        if ver >= 2:
            num_align = ver // 7 + 2
            raw -= (25 * num_align - 10) * num_align - 55
        capacity = raw // 8 - _QR_ECC_PER_BLOCK[ver - 1] * _QR_NUM_BLOCKS[ver - 1]
        if 4 + 8 + len(data) * 8 <= capacity * 8:
            break
    else:
        raise ValueError("text too long for the built-in QR generator")
    size = ver * 4 + 17

    # 1. Data bits: mode (byte), length, payload, terminator, padding.
    bits = []

    def put(value, count):
        bits.extend((value >> i) & 1 for i in range(count - 1, -1, -1))

    put(0b0100, 4)
    put(len(data), 8)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad = 0xEC
    while len(bits) < capacity * 8:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    # 2. Error correction, split into blocks and interleaved.
    num_blocks = _QR_NUM_BLOCKS[ver - 1]
    ecc_len = _QR_ECC_PER_BLOCK[ver - 1]
    short_blocks = num_blocks - (raw // 8) % num_blocks
    short_len = (raw // 8) // num_blocks - ecc_len
    divisor = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(num_blocks):
        d_len = short_len + (0 if i < short_blocks else 1)
        d = codewords[k:k + d_len]
        k += d_len
        ecc = _rs_remainder(d, divisor)
        if i < short_blocks:
            d = d + [0]  # placeholder so all blocks line up; skipped below
        blocks.append(d + ecc)
    final = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len or j >= short_blocks:
                final.append(blk[i])

    # 3. Fixed patterns.
    modules = [[False] * size for _ in range(size)]
    is_fn = [[False] * size for _ in range(size)]

    def set_fn(x, y, dark):
        modules[y][x] = dark
        is_fn[y][x] = True

    for i in range(size):
        set_fn(6, i, i % 2 == 0)
        set_fn(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    set_fn(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    if ver >= 2:
        cx = cy = size - 7
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                set_fn(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)

    def draw_format(grid, mask, mark):
        data_bits = mask  # error correction level M has format code 0b00
        rem = data_bits
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        fb = ((data_bits << 10) | rem) ^ 0x5412

        def put_fmt(x, y, dark):
            grid[y][x] = dark
            if mark:
                is_fn[y][x] = True

        bit = lambda i: ((fb >> i) & 1) != 0
        for i in range(6):
            put_fmt(8, i, bit(i))
        put_fmt(8, 7, bit(6))
        put_fmt(8, 8, bit(7))
        put_fmt(7, 8, bit(8))
        for i in range(9, 15):
            put_fmt(14 - i, 8, bit(i))
        for i in range(8):
            put_fmt(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            put_fmt(8, size - 15 + i, bit(i))
        put_fmt(8, size - 8, True)

    draw_format(modules, 0, True)

    # 4. Place the data bits in the zigzag pattern.
    all_bits = [(cw >> (7 - i)) & 1 for cw in final for i in range(8)]
    idx = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = size - 1 - vert if upward else vert
                if not is_fn[y][x] and idx < len(all_bits):
                    modules[y][x] = bool(all_bits[idx])
                    idx += 1
        right -= 2

    # 5. Pick the best of the 8 masks.
    def masked(m):
        grid = [row[:] for row in modules]
        for y in range(size):
            for x in range(size):
                if is_fn[y][x]:
                    continue
                inv = (
                    (x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0,
                    (x // 3 + y // 3) % 2 == 0, x * y % 2 + x * y % 3 == 0,
                    (x * y % 2 + x * y % 3) % 2 == 0, ((x + y) % 2 + x * y % 3) % 2 == 0,
                )[m]
                grid[y][x] = grid[y][x] != inv
        draw_format(grid, m, False)
        return grid

    def penalty(g):
        score = 0
        for lines in (g, [list(c) for c in zip(*g)]):
            for line in lines:
                run = 1
                for i in range(1, size):
                    if line[i] == line[i - 1]:
                        run += 1
                        score += 3 if run == 5 else (1 if run > 5 else 0)
                    else:
                        run = 1
                s = "".join("1" if v else "0" for v in line)
                score += 40 * (s.count("10111010000") + s.count("00001011101"))
        for y in range(size - 1):
            for x in range(size - 1):
                if g[y][x] == g[y][x + 1] == g[y + 1][x] == g[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in g)
        total = size * size
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
        return score

    return min((masked(m) for m in range(8)), key=penalty)


def qr_lines(text, quiet=2):
    """Render a QR code as lines of text that a phone camera can scan."""
    m = make_qr(text)
    width = len(m) + 2 * quiet
    grid = [[False] * width for _ in range(quiet)]
    grid += [[False] * quiet + row + [False] * quiet for row in m]
    grid += [[False] * width for _ in range(quiet)]
    if len(grid) % 2:
        grid.append([False] * width)

    use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    if use_color and os.name == "nt":
        os.system("")  # switches on ANSI colour support in the Windows console
    try:
        "█▀▄".encode(sys.stdout.encoding or "utf-8")
        use_blocks = True
    except (UnicodeError, LookupError):
        use_blocks = False

    lines = []
    if use_blocks:
        for y in range(0, len(grid), 2):
            row = ""
            for x in range(width):
                top, bottom = grid[y][x], grid[y + 1][x]
                if use_color:  # black on white, works on any terminal theme
                    row += "█" if top and bottom else "▀" if top else "▄" if bottom else " "
                else:  # assume a dark terminal: light modules are the filled ones
                    row += " " if top and bottom else "▄" if top else "▀" if bottom else "█"
            lines.append("\x1b[30;47m" + row + "\x1b[0m" if use_color else row)
    else:
        for row in grid:
            if use_color:
                lines.append("".join("\x1b[40m  " if v else "\x1b[47m  " for v in row) + "\x1b[0m")
            else:
                lines.append("".join("  " if v else "##" for v in row))
    return lines


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
        print("  On your PHONE, scan the QR code with the camera,")
        print("  or open Safari/Chrome and type the address:")
        for ip in ips:
            url = f"http://{ip}:{PORT}"
            print(f"\n    {url}\n")
            try:
                for line in qr_lines(url):
                    print("    " + line)
            except Exception:
                pass  # the QR code is a convenience; the address above still works
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