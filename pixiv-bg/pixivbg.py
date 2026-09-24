import json
import os
import random
import time
import urllib.parse
import urllib.request

BG_DIR = os.getenv("BG_DIR", "/bg")
REFRESH_HOURS = float(os.getenv("REFRESH_HOURS", "6"))
KEEP = int(os.getenv("KEEP", "6"))
MIN_RATIO = float(os.getenv("MIN_RATIO", "1.5"))
MAX_RATIO = float(os.getenv("MAX_RATIO", "2.0"))
MIN_WIDTH = int(os.getenv("MIN_WIDTH", "1200"))
MODE = os.getenv("MODE", "weekly")
CONTENT = os.getenv("CONTENT", "illust")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
RANK_URL = f"https://www.pixiv.net/ranking.php?format=json&mode={MODE}&content={CONTENT}&p=1"

current_index = os.path.join(BG_DIR, ".current")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def master_url(item):
    u = item["url"]
    return u.replace("https://i.pximg.net/c/480x960/", "https://i.pixiv.re/")


def refresh():
    try:
        body = fetch(RANK_URL)
        data = json.loads(body.decode("utf-8"))
    except Exception as e:
        log(f"ranking fetch failed: {e}")
        return False

    picked = []
    for it in data.get("contents", []):
        w, h = it.get("width", 0), it.get("height", 0)
        if w <= 0 or h <= 0:
            continue
        r = w / h
        if int(it.get("illust_page_count", 1) or 1) > 1:
            continue
        if not (MIN_RATIO <= r <= MAX_RATIO):
            continue
        if w < MIN_WIDTH:
            continue
        picked.append(it)
        if len(picked) >= KEEP:
            break

    if not picked:
        log("no 16:9 candidates this week")
        return False

    remains = set(os.listdir(BG_DIR))
    dropped = 0
    for it in picked:
        url = master_url(it)
        dest = os.path.join(BG_DIR, f"{it['illust_id']}.jpg")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            continue
        tmp = dest + ".tmp"
        try:
            img = fetch(url)
            if img[:3] != b"\xff\xd8\xff" and img[:4] != b"\x89PNG":
                raise ValueError("not an image")
            with open(tmp, "wb") as f:
                f.write(img)
            os.replace(tmp, dest)
            log(f"saved #{it['rank']} {it['illust_id']} {it['width']}x{it['height']} {url}")
            remains.discard(f"{it['illust_id']}.jpg")
        except Exception as e:
            log(f"download {it['illust_id']} failed: {e}")
            dropped += 1

    for name in list(remains):
        if name.endswith(".jpg") and name not in [f"{p['illust_id']}.jpg" for p in picked]:
            try:
                os.remove(os.path.join(BG_DIR, name))
                log(f"removed stale {name}")
            except OSError:
                pass
    return True


def set_current(name):
    dst = os.path.join(BG_DIR, "current.jpg")
    tmp = dst + ".tmp"
    try:
        if os.path.islink(tmp) or os.path.exists(tmp):
            os.remove(tmp)
        with open(tmp, "wb") as f:
            with open(os.path.join(BG_DIR, name), "rb") as g:
                f.write(g.read())
        os.replace(tmp, dst)
        with open(current_index, "w") as f:
            f.write(name)
        log(f"bg -> {name}")
    except OSError as e:
        log(f"rotate failed: {e}")


def build_index():
    imgs = sorted(
        n for n in os.listdir(BG_DIR) if n.endswith(".jpg") and n != "current.jpg"
    )
    with open(os.path.join(BG_DIR, "index.txt"), "w") as f:
        f.write("\n".join(imgs))
    log(f"index.txt -> {len(imgs)} images")


def ensure_initial():
    dst = os.path.join(BG_DIR, "current.jpg")
    imgs = sorted(n for n in os.listdir(BG_DIR) if n.endswith(".jpg") and n != "current.jpg")
    if not imgs:
        return
    if os.path.exists(dst) and os.path.getsize(dst) > 0 and imgs:
        return
    set_current(random.choice(imgs))


def main():
    os.makedirs(BG_DIR, exist_ok=True)
    while True:
        if refresh() or not os.listdir(BG_DIR):
            ensure_initial()
        build_index()
        time.sleep(REFRESH_HOURS * 3600)


if __name__ == "__main__":
    main()