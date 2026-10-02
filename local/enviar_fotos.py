"""Envia as fotos de exemplo (local/fotos_exemplo/) para os produtos, PELA API (que grava no S3).

    python local/enviar_fotos.py                    # API local
    python local/enviar_fotos.py http://IP-DA-EC2   # na AWS, depois do deploy

Só envia para produtos sem foto ou cuja foto sumiu do S3 (ex.: o S3 local foi reiniciado).
Ilustrações: Twemoji (CC-BY 4.0, https://github.com/jdecked/twemoji), ver fotos_exemplo/LICENCA.md.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
PHOTOS = Path(__file__).resolve().parent / "fotos_exemplo"


def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=15) as r:
        return json.loads(r.read())


def has_photo(item) -> bool:
    if not item["image_url"]:
        return False
    try:
        with urllib.request.urlopen(f"{API}{item['image_url']}", timeout=15) as r:
            return r.status == 200
    except urllib.error.HTTPError:
        return False


def upload(item_id: int, photo: Path):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{photo.name}\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode() + photo.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{API}/api/items/{item_id}/image", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def main(quiet: bool = False) -> int:
    if not any(PHOTOS.glob("*.jpg")):
        if not quiet:
            print("Nenhuma foto de exemplo em local/fotos_exemplo/ (imagens não são versionadas).\n"
                  "Gere com: python local/fotos_exemplo/gerar_fotos.py local/fotos_exemplo")
        return 0
    sent = 0
    for item in get("/api/items"):
        photo = PHOTOS / f"{item['sku']}.jpg"
        if photo.exists() and not has_photo(item):
            try:
                upload(item["id"], photo)
                sent += 1
            except urllib.error.HTTPError as err:
                print(f"  {item['sku']}: falhou ({json.loads(err.read()).get('message', err.code)})")
    if not quiet:
        print(f"{sent} foto(s) enviada(s) ao S3 pela API.")
    return sent


if __name__ == "__main__":
    main()
