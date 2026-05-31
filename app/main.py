from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from PIL import Image, ImageOps, ExifTags
from fractions import Fraction
import hashlib
import mimetypes
import os
import secrets
import socket
import subprocess
import threading
import time
import zipfile

app = FastAPI()

AP_SSID = "PhotoDrop-Pi"
AP_PASSWORD = "photodrop1234"
PHOTODROP_PORT = 80
SD_ROOT = Path("/mnt/sdcard")
THUMB_DIR = Path("./app/cache/thumbs")
ZIP_DIR = Path("./app/cache/zips")
THUMB_DIR.mkdir(parents=True, exist_ok=True)
ZIP_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

SESSION_TOKEN = secrets.token_hex(16)
SESSION_EXPIRE = time.time() + 86400
files_db = []
zip_jobs = {}
zip_jobs_lock = threading.Lock()
DISPLAY_MODE = "wifi"
IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
KNOWN_SCAN_DIRS = ["DCIM", "PRIVATE", "MP_ROOT", "AVCHD", "MISC", "PHOTOS", "PHOTO", "PICTURE", "PICTURES"]


def get_interface_ip(interface_name):
    try:
        result = subprocess.run(["ip", "-4", "addr", "show", interface_name], capture_output=True, text=True, timeout=3)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                ip = line.split()[1].split("/")[0]
                if not ip.startswith("127."):
                    return ip
    except Exception:
        pass
    return None


def get_ap_ip():
    return "10.42.0.1"


def get_lan_ip():
    for iface in ["wlan0", "eth0"]:
        ip = get_interface_ip(iface)
        if ip and not ip.startswith("10.42.0."):
            return ip
    return None


def get_local_ip():
    return get_interface_ip("wlan1") or get_lan_ip() or "127.0.0.1"


def make_session_url_for_ip(ip):
    if PHOTODROP_PORT == 80:
        return f"http://{ip}/s/{SESSION_TOKEN}"
    return f"http://{ip}:{PHOTODROP_PORT}/s/{SESSION_TOKEN}"


def make_ap_session_url():
    return make_session_url_for_ip(get_ap_ip())


def make_lan_session_url():
    lan_ip = get_lan_ip()
    if not lan_ip:
        return None
    return make_session_url_for_ip(lan_ip)


def make_session_url():
    return make_ap_session_url()


def refresh_session(expire_seconds=86400):
    global SESSION_TOKEN, SESSION_EXPIRE
    SESSION_TOKEN = secrets.token_hex(16)
    SESSION_EXPIRE = time.time() + expire_seconds
    return make_session_url()


def run_epaper(args, timeout=45):
    project_dir = str(Path(__file__).resolve().parents[1])
    return subprocess.run(args, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def show_wifi_qr():
    global DISPLAY_MODE
    try:
        result = run_epaper(["/usr/bin/python3", "app/epaper/display_wifi.py", AP_SSID, AP_PASSWORD, str(len(files_db))])
        if result.returncode == 0:
            DISPLAY_MODE = "wifi"
            print(f"[INFO] e-Paper Wi-Fi QR updated: {AP_SSID}")
        else:
            print("[WARN] e-Paper Wi-Fi QR update failed", result.stderr)
    except Exception as e:
        print(f"[WARN] e-Paper Wi-Fi QR update exception: {e}")


def show_gallery_qr():
    global DISPLAY_MODE
    if len(files_db) <= 0:
        show_wifi_qr()
        return
    url = make_ap_session_url()
    try:
        result = run_epaper(["/usr/bin/python3", "app/epaper/display_qr.py", url, str(len(files_db)), "AP"])
        if result.returncode == 0:
            DISPLAY_MODE = "gallery"
            print(f"[INFO] e-Paper AP Gallery QR updated: {url}")
        else:
            print("[WARN] e-Paper AP Gallery QR update failed", result.stderr)
    except Exception as e:
        print(f"[WARN] e-Paper AP Gallery QR update exception: {e}")


def show_lan_qr():
    global DISPLAY_MODE
    if len(files_db) <= 0:
        show_wifi_qr()
        return
    url = make_lan_session_url()
    if not url:
        print("[WARN] LAN IP not found. fallback to Wi-Fi QR")
        show_wifi_qr()
        return
    try:
        result = run_epaper(["/usr/bin/python3", "app/epaper/display_qr.py", url, str(len(files_db)), "LAN"])
        if result.returncode == 0:
            DISPLAY_MODE = "lan"
            print(f"[INFO] e-Paper LAN Gallery QR updated: {url}")
        else:
            print("[WARN] e-Paper LAN Gallery QR update failed", result.stderr)
    except Exception as e:
        print(f"[WARN] e-Paper LAN Gallery QR update exception: {e}")


def update_epaper(status="Ready"):
    if status == "No SD" or len(files_db) == 0:
        show_wifi_qr()
    else:
        show_gallery_qr()


def safe_exists(path: Path):
    try:
        return path.exists()
    except Exception as e:
        print(f"[WARN] cannot access: {path} {e}")
        return False


def safe_is_dir(path: Path):
    try:
        return path.exists() and path.is_dir()
    except Exception as e:
        print(f"[WARN] cannot access dir: {path} {e}")
        return False


def safe_is_file(path: Path):
    try:
        return path.is_file()
    except Exception as e:
        print(f"[WARN] cannot access file: {path} {e}")
        return False


def safe_stat(path: Path):
    try:
        return path.stat()
    except Exception as e:
        print(f"[WARN] cannot stat: {path} {e}")
        return None


def safe_resolve(path: Path):
    try:
        return str(path.resolve())
    except Exception as e:
        print(f"[WARN] cannot resolve: {path} {e}")
        return None


def safe_relative_to(path: Path, base: Path):
    try:
        return str(path.relative_to(base))
    except Exception:
        return str(path)


def is_hidden_or_system_file(path: Path):
    name = path.name
    return name.startswith("._") or name.startswith(".__") or name.startswith(".")


def is_valid_photo(path: Path):
    return safe_is_file(path) and not is_hidden_or_system_file(path) and path.suffix.lower() in IMAGE_EXTENSIONS


def get_scan_roots():
    roots = []
    if not safe_is_dir(SD_ROOT):
        return roots
    for dirname in KNOWN_SCAN_DIRS:
        candidate = SD_ROOT / dirname
        if safe_is_dir(candidate):
            roots.append(candidate)
    if not roots:
        roots.append(SD_ROOT)
    unique, seen = [], set()
    for root in roots:
        resolved = safe_resolve(root)
        if resolved and resolved not in seen:
            seen.add(resolved)
            unique.append(root)
    return unique


def iter_files_safely(root: Path):
    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and safe_is_dir(Path(dirpath) / d)]
            for filename in filenames:
                yield Path(dirpath) / filename
    except Exception as e:
        print(f"[WARN] cannot walk: {root} {e}")
        return


def make_file_id(path: Path, stat):
    raw = f"{path}:{stat.st_size}:{stat.st_mtime}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def scan_files():
    global files_db
    files_db = []
    if not safe_is_dir(SD_ROOT):
        print(f"[WARN] SD_ROOT not available: {SD_ROOT}")
        return
    scan_roots = get_scan_roots()
    print("[INFO] scan roots:", [str(r) for r in scan_roots])
    seen_paths = set()
    for root in scan_roots:
        for path in iter_files_safely(root):
            if not is_valid_photo(path):
                continue
            resolved_path = safe_resolve(path)
            if not resolved_path or resolved_path in seen_paths:
                continue
            seen_paths.add(resolved_path)
            stat = safe_stat(path)
            if not stat:
                continue
            files_db.append({"id": make_file_id(path, stat), "name": path.name, "path": str(path), "relative_path": safe_relative_to(path, SD_ROOT), "size": stat.st_size, "modified": stat.st_mtime})
    files_db.sort(key=lambda x: x["modified"], reverse=True)
    print(f"[INFO] scanned {len(files_db)} files")


def get_file(file_id: str):
    return next((f for f in files_db if f["id"] == file_id), None)


def get_file_index(file_id: str):
    for index, file_obj in enumerate(files_db):
        if file_obj["id"] == file_id:
            return index
    return None


def ensure_thumbnail(file_obj):
    src = Path(file_obj["path"])
    thumb_path = THUMB_DIR / f"{file_obj['id']}.jpg"
    if safe_exists(thumb_path):
        return thumb_path
    if not safe_exists(src):
        return None
    try:
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((320, 320))
            img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=75)
        return thumb_path
    except Exception as e:
        print(f"[WARN] thumbnail failed: {src} {e}")
        return None


def rational_to_float(value):
    try:
        if isinstance(value, tuple) and len(value) == 2:
            numerator, denominator = value
            return None if denominator == 0 else float(numerator) / float(denominator)
        if isinstance(value, Fraction):
            return float(value)
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return None if value.denominator == 0 else float(value.numerator) / float(value.denominator)
        return float(value)
    except Exception:
        return None


def format_exposure_time(value):
    number = rational_to_float(value)
    if number is None or number <= 0:
        return None
    if number >= 1:
        return f"{number:.1f}s"
    return f"1/{round(1 / number)}s"


def format_f_number(value):
    number = rational_to_float(value)
    return None if number is None else f"f/{number:.1f}"


def format_focal_length(value):
    number = rational_to_float(value)
    return None if number is None else f"{number:.0f}mm"


def format_ev(value):
    number = rational_to_float(value)
    if number is None:
        return None
    return f"+{number:.1f} EV" if number > 0 else f"{number:.1f} EV"


def format_file_size(size_bytes):
    size = float(size_bytes)
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{int(size)} B"


def get_exif_dict(path: Path):
    try:
        with Image.open(path) as img:
            raw_exif = img.getexif()
            image_size = img.size
            if not raw_exif:
                return {}, image_size
            exif = {}
            for tag_id, value in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if tag_name == "GPSInfo":
                    gps_data = {}
                    try:
                        for gps_id, gps_value in value.items():
                            gps_name = ExifTags.GPSTAGS.get(gps_id, str(gps_id))
                            gps_data[gps_name] = gps_value
                    except Exception:
                        gps_data = value
                    exif["GPSInfo"] = gps_data
                else:
                    exif[tag_name] = value
            return exif, image_size
    except Exception as e:
        print(f"[WARN] EXIF read failed: {path} {e}")
        return {}, None


def get_camera_label(exif):
    make = exif.get("Make")
    model = exif.get("Model")
    parts = []
    if make:
        parts.append(str(make).strip())
    if model:
        model_text = str(model).strip()
        if not parts or model_text.lower() not in parts[0].lower():
            parts.append(model_text)
    return " ".join(parts) if parts else None


def get_iso(exif):
    for key in ["ISOSpeedRatings", "PhotographicSensitivity", "RecommendedExposureIndex"]:
        value = exif.get(key)
        if value:
            return str(value)
    return None


def get_lens_label(exif):
    for key in ["LensModel", "LensMake", "LensSpecification"]:
        value = exif.get(key)
        if not value:
            continue
        if key == "LensSpecification":
            try:
                values = [rational_to_float(v) for v in value]
                if len(values) >= 4 and all(v for v in values[:4]):
                    min_focal, max_focal, min_f, max_f = values[:4]
                    if round(min_focal) == round(max_focal):
                        return f"{min_focal:.0f}mm f/{min_f:.1f}"
                    return f"{min_focal:.0f}-{max_focal:.0f}mm f/{min_f:.1f}-{max_f:.1f}"
            except Exception:
                pass
        return str(value).strip()
    return None


def gps_to_decimal(coord, ref):
    try:
        if not coord or len(coord) != 3:
            return None
        degrees = rational_to_float(coord[0])
        minutes = rational_to_float(coord[1])
        seconds = rational_to_float(coord[2])
        if degrees is None or minutes is None or seconds is None:
            return None
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ["S", "W"]:
            decimal = -decimal
        return decimal
    except Exception:
        return None


def extract_gps_info(exif):
    gps = exif.get("GPSInfo")
    result = {"has_gps": False, "latitude": None, "longitude": None, "display": "なし", "map_url": None}
    if not gps or not isinstance(gps, dict):
        return result
    latitude = gps_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
    longitude = gps_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
    if latitude is None or longitude is None:
        result.update({"has_gps": True, "display": "あり（座標は取得できませんでした）"})
        return result
    result.update({"has_gps": True, "latitude": latitude, "longitude": longitude, "display": f"{latitude:.6f}, {longitude:.6f}", "map_url": f"https://maps.google.com/?q={latitude:.6f},{longitude:.6f}"})
    return result


def extract_photo_info(file_obj):
    path = Path(file_obj["path"])
    info = {"summary": [], "details": [], "has_exif": False, "gps_status": "なし", "gps_map_url": None}
    stat = safe_stat(path)
    if stat:
        info["details"].append({"label": "File size", "value": format_file_size(stat.st_size)})
    exif, image_size = get_exif_dict(path)
    if image_size:
        width, height = image_size
        info["summary"].append({"label": "Size", "value": f"{width} × {height}"})
    if not exif:
        return info
    info["has_exif"] = True
    fields = [
        ("Camera", get_camera_label(exif)),
        ("Lens", get_lens_label(exif)),
        ("Date", exif.get("DateTimeOriginal") or exif.get("DateTimeDigitized") or exif.get("DateTime")),
        ("ISO", get_iso(exif)),
        ("Aperture", format_f_number(exif.get("FNumber"))),
        ("Shutter", format_exposure_time(exif.get("ExposureTime"))),
        ("Focal length", format_focal_length(exif.get("FocalLength"))),
    ]
    for label, value in fields:
        if value:
            info["summary"].append({"label": label, "value": str(value)})
    detail_fields = [
        ("Exposure bias", format_ev(exif.get("ExposureBiasValue"))),
        ("Exposure program", exif.get("ExposureProgram")),
        ("Metering", exif.get("MeteringMode")),
        ("White balance", "Auto" if exif.get("WhiteBalance") == 0 else ("Manual" if exif.get("WhiteBalance") is not None else None)),
        ("Software", exif.get("Software")),
        ("Orientation", exif.get("Orientation")),
    ]
    for label, value in detail_fields:
        if value:
            info["details"].append({"label": label, "value": str(value)})
    gps_info = extract_gps_info(exif)
    info["gps_status"] = gps_info["display"]
    info["gps_map_url"] = gps_info["map_url"]
    info["details"].append({"label": "GPS", "value": gps_info["display"]})
    return info


def cleanup_old_zip_jobs(max_age_seconds=3600):
    now = time.time()
    with zip_jobs_lock:
        old_job_ids = [job_id for job_id, job in zip_jobs.items() if now - job.get("created_at", now) > max_age_seconds]
        for job_id in old_job_ids:
            job = zip_jobs.pop(job_id, None)
            if job and job.get("zip_path"):
                try:
                    Path(job["zip_path"]).unlink(missing_ok=True)
                except Exception:
                    pass


def create_zip_job(file_ids):
    cleanup_old_zip_jobs()
    if not file_ids:
        raise HTTPException(status_code=400, detail="No files selected")
    if len(file_ids) > 300:
        raise HTTPException(status_code=400, detail="Too many files selected. Max 300 files.")
    selected_files = []
    for file_id in file_ids:
        file_obj = get_file(file_id)
        if file_obj and safe_exists(Path(file_obj["path"])):
            selected_files.append(file_obj)
    if not selected_files:
        raise HTTPException(status_code=400, detail="No valid files selected")
    total_bytes = sum(f["size"] for f in selected_files)
    if total_bytes > 3 * 1024 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Selected files are too large. Max 3GB.")
    job_id = secrets.token_hex(12)
    zip_path = ZIP_DIR / f"photodrop_{job_id}.zip"
    with zip_jobs_lock:
        zip_jobs[job_id] = {"job_id": job_id, "status": "queued", "created_at": time.time(), "total_files": len(selected_files), "done_files": 0, "total_bytes": total_bytes, "done_bytes": 0, "progress": 0, "zip_path": str(zip_path), "error": None, "download_url": None}
    threading.Thread(target=build_zip_file, args=(job_id, selected_files, zip_path), daemon=True).start()
    return job_id


def build_zip_file(job_id, selected_files, zip_path):
    try:
        with zip_jobs_lock:
            zip_jobs[job_id]["status"] = "running"
        used_names = {}
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            done_bytes = 0
            for index, file_obj in enumerate(selected_files, start=1):
                path = Path(file_obj["path"])
                if not safe_exists(path):
                    continue
                arcname = file_obj.get("relative_path") or file_obj["name"]
                if arcname in used_names:
                    used_names[arcname] += 1
                    stem, suffix, parent = Path(arcname).stem, Path(arcname).suffix, str(Path(arcname).parent)
                    new_name = f"{stem}_{used_names[arcname]}{suffix}"
                    arcname = str(Path(parent) / new_name) if parent and parent != "." else new_name
                else:
                    used_names[arcname] = 1
                zf.write(path, arcname=arcname)
                done_bytes += file_obj["size"]
                with zip_jobs_lock:
                    zip_jobs[job_id].update({"done_files": index, "done_bytes": done_bytes, "progress": int(index / len(selected_files) * 100)})
        with zip_jobs_lock:
            zip_jobs[job_id].update({"status": "done", "progress": 100, "download_url": f"/api/download/zip/file/{job_id}"})
    except Exception as e:
        with zip_jobs_lock:
            if job_id in zip_jobs:
                zip_jobs[job_id].update({"status": "error", "error": str(e)})


@app.on_event("startup")
async def on_startup():
    try:
        scan_files()
        refresh_session()
        show_gallery_qr() if len(files_db) > 0 else show_wifi_qr()
    except Exception as e:
        print(f"[WARN] startup failed: {e}")


@app.get("/", response_class=HTMLResponse)
async def root():
    lan_ip = get_lan_ip()
    lan_url = make_lan_session_url()
    return f"""
    <!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>PhotoDrop Pi</title>
    <style>*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f4f4f2;color:#111;padding:24px}}.box{{max-width:560px;margin:0 auto;background:#fff;border:1px solid #d9d9d6;padding:24px}}h1{{margin:0 0 8px;font-size:28px;letter-spacing:-.04em}}p{{color:#555;line-height:1.55;word-break:break-all}}form{{width:100%;margin:0}}a,button{{display:block;width:100%;box-sizing:border-box;margin-top:12px;padding:13px;background:#111;color:#fff;text-decoration:none;border:none;text-align:center;font-weight:700;font-size:15px;font-family:inherit}}.secondary{{background:#ededeb;color:#111}}.meta{{margin-top:18px;padding-top:12px;border-top:1px solid #ddd}}.small{{font-size:13px;color:#777}}.site-footer{{margin-top:28px;padding:18px 0 6px;color:#777;font-size:12px;text-align:center;letter-spacing:.02em}}</style></head>
    <body><div class="box"><h1>PhotoDrop Pi</h1><p>Wi-Fi: {AP_SSID}</p><p>Photos: {len(files_db)}</p><p>Display: {DISPLAY_MODE}</p><div class="meta"><p><strong>AP Gallery:</strong><br>{make_ap_session_url()}</p><p><strong>LAN IP:</strong><br>{lan_ip or "Not connected"}</p><p><strong>LAN Gallery:</strong><br>{lan_url or "Not available"}</p></div><a href="/s/{SESSION_TOKEN}">Open Gallery</a><form method="post" action="/api/admin/display/wifi"><button class="secondary" type="submit">Show Wi-Fi QR</button></form><form method="post" action="/api/admin/display/gallery"><button class="secondary" type="submit">Show AP Gallery QR</button></form><form method="post" action="/api/admin/display/lan"><button class="secondary" type="submit">Show LAN Gallery QR</button></form><form method="post" action="/api/admin/display/toggle"><button class="secondary" type="submit">Toggle QR</button></form><form method="post" action="/api/admin/session/refresh"><button class="secondary" type="submit">Refresh Session</button></form><form method="post" action="/api/admin/rescan"><button class="secondary" type="submit">Rescan SD</button></form><p class="small">Button toggle: Wi-Fi QR → AP Gallery QR → LAN Gallery QR → Wi-Fi QR</p><footer class="site-footer">© 2026 PhotoDrop-Pi / YUK_KND</footer></div></body></html>
    """


@app.get("/s/{token}", response_class=HTMLResponse)
async def gallery(request: Request, token: str):
    if token != SESSION_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    if time.time() > SESSION_EXPIRE:
        raise HTTPException(status_code=410, detail="Session expired")
    return templates.TemplateResponse(request=request, name="gallery.html", context={"token": token, "total": len(files_db), "expires_in": int(max(0, SESSION_EXPIRE - time.time()))})


@app.get("/p/{file_id}", response_class=HTMLResponse)
async def photo_view(request: Request, file_id: str):
    file_obj = get_file(file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    index = get_file_index(file_id)
    prev_id = files_db[index - 1]["id"] if index is not None and index > 0 else None
    next_id = files_db[index + 1]["id"] if index is not None and index < len(files_db) - 1 else None
    return templates.TemplateResponse(request=request, name="photo.html", context={"file": file_obj, "prev_id": prev_id, "next_id": next_id, "total": len(files_db), "gallery_url": f"/s/{SESSION_TOKEN}", "photo_info": extract_photo_info(file_obj)})


@app.get("/api/files")
async def list_files(limit: int = Query(60, ge=1, le=200), offset: int = Query(0, ge=0)):
    total = len(files_db)
    items = files_db[offset:offset + limit]
    return {"items": [{"id": f["id"], "name": f["name"], "size": f["size"], "relative_path": f.get("relative_path", f["name"]), "view_page_url": f"/p/{f['id']}", "view_url": f"/api/files/{f['id']}/view", "download_url": f"/api/files/{f['id']}/download", "thumbnail_url": f"/api/files/{f['id']}/thumbnail"} for f in items], "total": total, "limit": limit, "offset": offset, "next_offset": offset + limit if offset + limit < total else None}


@app.get("/api/files/{file_id}/thumbnail")
async def thumbnail(file_id: str):
    file_obj = get_file(file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    thumb = ensure_thumbnail(file_obj)
    if thumb is None:
        raise HTTPException(status_code=500, detail="Thumbnail generation failed")
    return FileResponse(thumb, media_type="image/jpeg")


@app.get("/api/files/{file_id}/view")
async def view_image(file_id: str):
    file_obj = get_file(file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(file_obj["path"])
    if not safe_exists(path):
        raise HTTPException(status_code=404, detail="Source file missing")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "image/jpeg", filename=file_obj["name"], headers={"Content-Disposition": f'inline; filename="{file_obj["name"]}"'})


@app.get("/api/files/{file_id}/download")
async def download(file_id: str):
    file_obj = get_file(file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(file_obj["path"])
    if not safe_exists(path):
        raise HTTPException(status_code=404, detail="Source file missing")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, filename=file_obj["name"], media_type=media_type or "application/octet-stream")


@app.get("/api/files/{file_id}/exif")
async def exif_api(file_id: str):
    file_obj = get_file(file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    return extract_photo_info(file_obj)


@app.post("/api/download/zip/start")
async def zip_start(file_ids: list[str]):
    job_id = create_zip_job(file_ids)
    with zip_jobs_lock:
        return zip_jobs[job_id].copy()


@app.get("/api/download/zip/status/{job_id}")
async def zip_status(job_id: str):
    with zip_jobs_lock:
        job = zip_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ZIP job not found")
        return job.copy()


@app.get("/api/download/zip/file/{job_id}")
async def zip_file(job_id: str):
    with zip_jobs_lock:
        job = zip_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ZIP job not found")
        if job["status"] != "done":
            raise HTTPException(status_code=409, detail="ZIP is not ready")
        zip_path = Path(job["zip_path"])
    if not safe_exists(zip_path):
        raise HTTPException(status_code=404, detail="ZIP file missing")
    return FileResponse(zip_path, filename="photodrop.zip", media_type="application/zip")


@app.post("/api/admin/rescan")
async def rescan():
    scan_files()
    refresh_session()
    update_epaper("Ready")
    return {"ok": True, "photo_count": len(files_db), "display_mode": DISPLAY_MODE, "url": make_session_url(), "ap_url": make_ap_session_url(), "lan_url": make_lan_session_url()}


@app.post("/api/admin/session/refresh")
async def session_refresh():
    url = refresh_session()
    if DISPLAY_MODE == "gallery":
        show_gallery_qr()
    elif DISPLAY_MODE == "lan":
        show_lan_qr()
    return {"ok": True, "token": SESSION_TOKEN, "url": url, "ap_url": make_ap_session_url(), "lan_url": make_lan_session_url(), "expires_in": int(SESSION_EXPIRE - time.time()), "display_mode": DISPLAY_MODE}


@app.post("/api/admin/epaper/update")
async def epaper_update():
    update_epaper("Ready" if len(files_db) > 0 else "No SD")
    return {"ok": True, "url": make_session_url(), "ap_url": make_ap_session_url(), "lan_url": make_lan_session_url(), "photo_count": len(files_db), "display_mode": DISPLAY_MODE}


@app.post("/api/admin/display/wifi")
async def display_wifi():
    show_wifi_qr()
    return {"ok": True, "display_mode": DISPLAY_MODE, "ap_ssid": AP_SSID}


@app.post("/api/admin/display/gallery")
async def display_gallery():
    if len(files_db) <= 0:
        show_wifi_qr()
        return {"ok": False, "reason": "no_photos", "display_mode": DISPLAY_MODE}
    show_gallery_qr()
    return {"ok": True, "display_mode": DISPLAY_MODE, "url": make_ap_session_url(), "photo_count": len(files_db)}


@app.post("/api/admin/display/lan")
async def display_lan():
    if len(files_db) <= 0:
        show_wifi_qr()
        return {"ok": False, "reason": "no_photos", "display_mode": DISPLAY_MODE}
    lan_url = make_lan_session_url()
    if not lan_url:
        return {"ok": False, "reason": "lan_ip_not_found", "display_mode": DISPLAY_MODE, "lan_ip": None, "lan_url": None}
    show_lan_qr()
    return {"ok": True, "display_mode": DISPLAY_MODE, "url": lan_url, "photo_count": len(files_db), "lan_ip": get_lan_ip()}


@app.post("/api/admin/display/toggle")
async def display_toggle():
    lan_url = make_lan_session_url()
    if DISPLAY_MODE == "wifi":
        show_gallery_qr() if len(files_db) > 0 else show_wifi_qr()
    elif DISPLAY_MODE == "gallery":
        show_lan_qr() if len(files_db) > 0 and lan_url else show_wifi_qr()
    elif DISPLAY_MODE == "lan":
        show_wifi_qr()
    else:
        show_wifi_qr()
    return {"ok": True, "display_mode": DISPLAY_MODE, "ap_url": make_ap_session_url(), "lan_ip": get_lan_ip(), "lan_url": make_lan_session_url(), "photo_count": len(files_db), "ap_ssid": AP_SSID}


@app.post("/api/admin/sd/removed")
async def sd_removed():
    global files_db
    files_db = []
    refresh_session()
    show_wifi_qr()
    return {"ok": True, "state": "sd_removed", "display_mode": DISPLAY_MODE}


@app.get("/api/status")
async def status():
    remaining = int(max(0, SESSION_EXPIRE - time.time()))
    return {"state": "ready", "sd_root": str(SD_ROOT), "scan_roots": [str(p) for p in get_scan_roots()], "sd_mounted": safe_is_dir(SD_ROOT), "photo_count": len(files_db), "ap_ssid": AP_SSID, "session_token": SESSION_TOKEN, "session_url": make_session_url(), "ap_url": make_ap_session_url(), "lan_ip": get_lan_ip(), "lan_url": make_lan_session_url(), "session_expires_in": remaining, "ip": get_local_ip(), "display_mode": DISPLAY_MODE}
