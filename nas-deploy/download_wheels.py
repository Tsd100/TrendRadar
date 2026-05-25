"""Download all wheels from uv.lock using Chinese mirrors for speed."""
import toml
import urllib.request
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

LOCK_PATH = os.path.join(os.path.dirname(__file__), '..', 'uv.lock')
DEST = os.path.join(os.path.dirname(__file__), 'offline-deps', 'wheels')

# Chinese mirrors (faster for domestic users)
MIRRORS = [
    "https://pypi.tuna.tsinghua.edu.cn/packages",
    "https://mirrors.aliyun.com/pypi/packages",
    "https://mirrors.cloud.tencent.com/pypi/packages",
]

os.makedirs(DEST, exist_ok=True)

with open(LOCK_PATH, 'r', encoding='utf-8') as f:
    lock = toml.load(f)

packages = lock.get('package', [])
print(f"Total packages in lock: {len(packages)}")

# Collect download tasks
tasks = []
for pkg in packages:
    name = pkg.get('name', 'unknown')
    wheels = pkg.get('wheels', [])
    if not wheels:
        continue

    # Priority: cp312 manylinux x86_64 > any manylinux x86_64 > any
    chosen = None
    for w in wheels:
        url = w['url']
        if 'manylinux' in url and 'x86_64' in url and 'cp312' in url:
            chosen = w
            break
    if not chosen:
        for w in wheels:
            url = w['url']
            if 'manylinux' in url and 'x86_64' in url:
                chosen = w
                break
    if not chosen:
        for w in wheels:
            if '-any.whl' in url or 'py3-none-any' in url:
                chosen = w
                break
    if not chosen and wheels:
        chosen = wheels[0]

    if chosen:
        filename = os.path.basename(chosen['url'])
        # Extract the path part after /packages/
        # URL format: https://files.pythonhosted.org/packages/ab/cd/.../file.whl
        path_part = chosen['url'].split('/packages/')[-1] if '/packages/' in chosen['url'] else None
        filepath = os.path.join(DEST, filename)
        if not os.path.exists(filepath):
            tasks.append((name, path_part, filename, chosen['hash']))

print(f"Already cached: {len(packages) - len(tasks)}, Need to download: {len(tasks)}")

def download_pkg(name, path_part, filename, expected_hash):
    """Download from mirrors, fall back to original PyPI."""
    urls = []
    if path_part:
        for mirror in MIRRORS:
            urls.append(f"{mirror}/{path_part}")
        # Original PyPI as fallback
        urls.append(f"https://files.pythonhosted.org/packages/{path_part}")
    else:
        return f"SKIP {name} - no path"

    filepath = os.path.join(DEST, filename)
    for i, url in enumerate(urls):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'TrendRadar/1.0'})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            with open(filepath, 'wb') as f:
                f.write(data)
            size_mb = len(data) / (1024 * 1024)
            return f"OK {name}: {filename} ({size_mb:.1f}MB) [mirror {i}]"
        except Exception as e:
            if i == len(urls) - 1:
                return f"FAIL {name}: {filename} - {e}"
            continue
    return f"FAIL {name}: unknown error"

# Download in parallel with 8 threads
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {
        executor.submit(download_pkg, name, path, fname, h): name
        for name, path, fname, h in tasks
    }

    done = 0
    for future in as_completed(futures):
        done += 1
        result = future.result()
        if done % 10 == 0 or 'FAIL' in result:
            print(f"[{done}/{len(tasks)}] {result}")

print(f"\nDone! Downloaded to: {DEST}")
print(f"Total files: {len(os.listdir(DEST))}")
