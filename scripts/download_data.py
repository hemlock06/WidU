"""공개 검증 데이터셋 수집기.

개방형은 자동 다운로드, 등록 필요분은 안내 출력.
사용:
    python scripts/download_data.py --sisfall --ppgdalia
    python scripts/download_data.py --all
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# (이름, URL 후보들, 압축여부, 라이선스)
SOURCES = {
    "sisfall": {
        "urls": [
            # GitHub 릴리스 미러(직링크, 검증됨 213MB). 중첩 zip 구조.
            "https://github.com/BIng2325/SisFall/releases/download/dataset/SisFall.zip",
            "http://sistemic.udea.edu.co/wp-content/uploads/2016/11/SisFall_dataset.zip",
        ],
        "out": DATA / "SisFall",
        "license": "연구용 무료 (UDEA)",
        "note": "GitHub 릴리스 미러 사용. 차단 시 Kaggle 'sis-fall-original-dataset'.",
    },
    "ppgdalia": {
        "urls": [
            "https://archive.ics.uci.edu/static/public/495/ppg+dalia.zip",
            "https://zenodo.org/records/3902728/files/PPG_FieldStudy.zip",
        ],
        "out": DATA / "PPG_DaLiA",
        "license": "CC BY 4.0",
        "note": "UCI/Zenodo 개방.",
    },
    "wesad": {
        "urls": [
            "https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download",
        ],
        "out": DATA / "WESAD",
        "license": "연구용 무료",
        "note": "스트레스 라벨 — HR 맥락 반응 보조검증.",
    },
}

REGISTRATION_ONLY = {
    "fallalld": "IEEE DataPort 'FallAllD' (손목 포함 IMU, 등록 필요)",
    "shhs": "NSRR 'Sleep Heart Health Study' (산소탈포화, 등록 필요)",
    "mimic": "PhysioNet MIMIC-IV Waveform (자격+CITI 교육 필요)",
    "vitaldb": "API 직접 사용 — 다운로드 불필요 (widu.datasets.vitaldb)",
}


def _download(url: str, dst: Path) -> bool:
    import requests
    try:
        print(f"  ↓ {url}")
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    실패: {e}")
        return False


def fetch(name: str):
    src = SOURCES[name]
    out = src["out"]
    out.mkdir(parents=True, exist_ok=True)
    zip_path = DATA / f"{name}.zip"
    print(f"[{name}] 라이선스={src['license']}  {src['note']}")
    ok = False
    for url in src["urls"]:
        if _download(url, zip_path):
            ok = True
            break
    if not ok:
        print(f"  ⚠ 자동 다운로드 실패 → 수동 안내: {src['note']}")
        return
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out)
        # 중첩 zip(예: SisFall 릴리스) 재귀 해제(1단계)
        for inner in list(out.rglob("*.zip")):
            try:
                with zipfile.ZipFile(inner) as z:
                    z.extractall(inner.parent)
            except zipfile.BadZipFile:
                pass
        n_txt = len(list(out.rglob("*.txt")))
        print(f"  ✓ 압축 해제 → {out}  ({n_txt} txt)")
    except zipfile.BadZipFile:
        print(f"  ⚠ zip 아님(로그인 페이지 가능) → 수동 확인 필요: {zip_path}")


def main():
    ap = argparse.ArgumentParser()
    for k in SOURCES:
        ap.add_argument(f"--{k}", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    chosen = [k for k in SOURCES if getattr(a, k)] or (list(SOURCES) if a.all else [])
    if not chosen:
        ap.print_help()
        print("\n등록 필요(수동):")
        for k, v in REGISTRATION_ONLY.items():
            print(f"  - {k}: {v}")
        return
    for k in chosen:
        fetch(k)


if __name__ == "__main__":
    main()
