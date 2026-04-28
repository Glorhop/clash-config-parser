import os
import tempfile

from .paths import DOWNLOADS_DIR


DATA_FILES = [
    {
        "filename": "geosite.dat",
        "label": "geosite.dat",
        "kind": "规则数据",
    },
    {
        "filename": "Country.mmdb",
        "label": "Country.mmdb",
        "kind": "GeoIP 数据",
    },
]

MIHOMO_FILES = {
    "amd64": {
        "filename": "mihomo-linux-amd64-v3-v1.19.18.deb",
        "label": "Mihomo Linux amd64",
        "kind": "Debian 包",
        "install_type": "deb",
    },
    "arm64": {
        "filename": "mihomo-linux-arm64-alpha-56c3462.gz",
        "label": "Mihomo Linux arm64",
        "kind": "Gzip 二进制",
        "install_type": "gz",
    },
}

ARCH_ALIASES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv8": "arm64",
}

INSTALL_SCRIPTS = [
    {"name": "mihomo.sh", "label": "自动下载", "arch": "auto"},
    {"name": "mihomo-amd64.sh", "label": "amd64 下载", "arch": "amd64"},
    {"name": "mihomo-arm64.sh", "label": "arm64 下载", "arch": "arm64"},
]


def normalize_arch(value):
    if not value:
        return None
    return ARCH_ALIASES.get(str(value).strip().lower())


def allowed_download_filenames():
    names = {item["filename"] for item in DATA_FILES}
    names.update(item["filename"] for item in MIHOMO_FILES.values())
    return names


def download_file_path(filename):
    if filename not in allowed_download_filenames():
        return None
    path = DOWNLOADS_DIR / filename
    if not path.is_file():
        return None
    return path


def save_download_file(filename, file_storage):
    path = _allowed_file_path(filename)
    if path is None:
        return None

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DOWNLOADS_DIR, prefix=f".{filename}.", suffix=".tmp")
    os.close(fd)
    try:
        file_storage.save(tmp_path)
        size = os.path.getsize(tmp_path)
        if size <= 0:
            raise ValueError("uploaded file is empty")
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
        return _file_info(path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def list_download_entries():
    entries = []
    for item in DATA_FILES:
        entries.append(_entry(item, f"/downloads/{item['filename']}"))
    for arch, item in MIHOMO_FILES.items():
        data = dict(item)
        data["arch"] = arch
        entries.append(_entry(data, f"/downloads/mihomo/{arch}"))
    return entries


def list_script_entries():
    return [
        {
            "name": item["name"],
            "label": item["label"],
            "arch": item["arch"],
            "url": f"/install/{item['name']}",
        }
        for item in INSTALL_SCRIPTS
    ]


def build_installer_script(base_url: str, forced_arch=None) -> str:
    base_url = base_url.rstrip("/")
    arch_block = _forced_arch_block(forced_arch) if forced_arch else _auto_arch_block()
    return f"""#!/bin/sh
set -eu

BASE_URL="${{MIHOMO_BASE_URL:-{base_url}}}"
TARGET_DIR="${{MIHOMO_TARGET_DIR:-$(pwd)}}"

fail() {{
  echo "ERROR: $*" >&2
  exit 1
}}

download() {{
  url="$1"
  dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$dest" "$url"
  else
    fail "curl or wget is required"
  fi
}}

{arch_block}

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT INT TERM

mkdir -p "$TARGET_DIR"

download "$BASE_URL/downloads/$MIHOMO_FILE" "$tmpdir/$MIHOMO_FILE"

if [ "$MIHOMO_INSTALL_TYPE" = "deb" ]; then
  command -v dpkg-deb >/dev/null 2>&1 || fail "dpkg-deb is required to extract $MIHOMO_FILE"
  mkdir -p "$tmpdir/deb"
  dpkg-deb -x "$tmpdir/$MIHOMO_FILE" "$tmpdir/deb"
  [ -x "$tmpdir/deb/usr/bin/mihomo" ] || fail "mihomo binary not found in $MIHOMO_FILE"
  install -m 0755 "$tmpdir/deb/usr/bin/mihomo" "$TARGET_DIR/mihomo"
else
  if command -v gzip >/dev/null 2>&1; then
    gzip -dc "$tmpdir/$MIHOMO_FILE" > "$tmpdir/mihomo"
  elif command -v gunzip >/dev/null 2>&1; then
    gunzip -c "$tmpdir/$MIHOMO_FILE" > "$tmpdir/mihomo"
  else
    fail "gzip or gunzip is required to extract $MIHOMO_FILE"
  fi
  install -m 0755 "$tmpdir/mihomo" "$TARGET_DIR/mihomo"
fi

download "$BASE_URL/downloads/geosite.dat" "$tmpdir/geosite.dat"
download "$BASE_URL/downloads/Country.mmdb" "$tmpdir/Country.mmdb"
install -m 0644 "$tmpdir/geosite.dat" "$TARGET_DIR/geosite.dat"
install -m 0644 "$tmpdir/Country.mmdb" "$TARGET_DIR/Country.mmdb"

if [ -x "$TARGET_DIR/mihomo" ]; then
  "$TARGET_DIR/mihomo" -v || true
fi

echo "mihomo prepared for $MIHOMO_ARCH"
echo "files saved to $TARGET_DIR"
echo "  $TARGET_DIR/mihomo"
echo "  $TARGET_DIR/geosite.dat"
echo "  $TARGET_DIR/Country.mmdb"
"""


def _entry(item, url):
    path = DOWNLOADS_DIR / item["filename"]
    info = _file_info(path)
    return {
        "filename": item["filename"],
        "label": item["label"],
        "kind": item["kind"],
        "url": url,
        "upload_url": f"/api/downloads/{item['filename']}",
        "size": info["size"],
        "modified_at": info["modified_at"],
        "exists": info["exists"],
        **({"arch": item["arch"]} if item.get("arch") else {}),
    }


def _allowed_file_path(filename):
    if filename not in allowed_download_filenames():
        return None
    return DOWNLOADS_DIR / filename


def _file_info(path):
    if not path.is_file():
        return {"exists": False, "size": None, "modified_at": None}
    stat = path.stat()
    return {"exists": True, "size": stat.st_size, "modified_at": int(stat.st_mtime)}


def _auto_arch_block():
    return f"""case "$(uname -m)" in
  x86_64|amd64)
    MIHOMO_ARCH="amd64"
    MIHOMO_FILE="{MIHOMO_FILES['amd64']['filename']}"
    MIHOMO_INSTALL_TYPE="{MIHOMO_FILES['amd64']['install_type']}"
    ;;
  aarch64|arm64|armv8*)
    MIHOMO_ARCH="arm64"
    MIHOMO_FILE="{MIHOMO_FILES['arm64']['filename']}"
    MIHOMO_INSTALL_TYPE="{MIHOMO_FILES['arm64']['install_type']}"
    ;;
  *)
    fail "unsupported architecture: $(uname -m)"
    ;;
esac"""


def _forced_arch_block(arch):
    item = MIHOMO_FILES[arch]
    return f"""MIHOMO_ARCH="{arch}"
MIHOMO_FILE="{item['filename']}"
MIHOMO_INSTALL_TYPE="{item['install_type']}" """
