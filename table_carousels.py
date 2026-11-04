"""Каруселі з таблиці «Threads публікатор» (Make B2): 6 слайдів на пост у неоновому стилі.
Тексти слайдів лежать у table_carousels.json (ключ = № рядка таблиці).
Результат: <out>/t/p<№>/s1..s6.jpg (1080x1350). Make B2 бере саме ці адреси.
"""
import hashlib
import json
from pathlib import Path

import neon_core as NC

ROOT = Path(__file__).resolve().parent


def render_all(out_dir):
    data = json.loads((ROOT / "table_carousels.json").read_text(encoding="utf-8"))
    w, h = NC.FORMATS["instagram"]
    done = 0
    for num, slides in data.items():
        key = hashlib.sha1(f"p{num}".encode()).hexdigest()
        poses = NC.pick_poses(key, len(slides))
        d = Path(out_dir) / "t" / f"p{num}"
        d.mkdir(parents=True, exist_ok=True)
        for i, pose in enumerate(poses, 1):
            img = NC.render(slides, "instagram", w, h, i, len(slides), pose, key)
            img.save(d / f"s{i}.jpg", "JPEG", quality=88, subsampling=0, optimize=True)
        done += 1
    return done


if __name__ == "__main__":
    import sys
    print("table carousels:", render_all(sys.argv[1] if len(sys.argv) > 1 else "site"))
