from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve


RECORD_BASE = "https://zenodo.org/records/14986870/files"
APP_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = APP_ROOT / "user_data" / "input" / "sample-1_Y7_T"

FILES = [
    ("adata_ST_Y7_T_raw.h5ad", EXAMPLE_ROOT / "ST" / "adata_ST_Y7_T_raw.h5ad"),
    ("Y7_T_pos.imzML", EXAMPLE_ROOT / "SM" / "Y7_T_pos.imzML"),
    ("Y7_T_pos.ibd", EXAMPLE_ROOT / "SM" / "Y7_T_pos.ibd"),
    ("Y7_T_neg.imzML", EXAMPLE_ROOT / "SM" / "Y7_T_neg.imzML"),
    ("Y7_T_neg.ibd", EXAMPLE_ROOT / "SM" / "Y7_T_neg.ibd"),
]


def download_file(file_name, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        print(f"[SKIP] {destination} already exists")
        return

    url = f"{RECORD_BASE}/{file_name}?download=1"
    tmp_path = destination.with_suffix(destination.suffix + ".download")
    if tmp_path.exists():
        tmp_path.unlink()

    print(f"[GET] {url}")
    urlretrieve(url, tmp_path)
    tmp_path.replace(destination)
    print(f"[OK]  {destination}")


def main():
    print(f"SpatialMeta Y7_T example root: {EXAMPLE_ROOT}")
    for file_name, destination in FILES:
        download_file(file_name, destination)


if __name__ == "__main__":
    try:
        main()
    except URLError as exc:
        raise SystemExit(f"Download failed: {exc}") from exc
