"""그린스크린 스프라이트 시트를 프레임별 투명 PNG로 자르기.

사용법: python tools/slice_sprites.py <시트.png> <상태이름> [출력폴더]
예:     python tools/slice_sprites.py sheet.png idle   ->  sprites/idle_01.png, idle_02.png ...
캐릭터들이 가로로 나란히 있고 사이에 초록 빈칸이 있으면 자동으로 개수를 찾음.
"""
import os
import sys

import numpy as np
from PIL import Image

OUT_SIZE = 256  # 저장 크기(정사각형)
CELL = 520      # 원본에서 자를 칸 크기(px). 모든 시트에 같게 써야 상태마다 캐릭터 크기가 일정함


def main():
    src, name = sys.argv[1], sys.argv[2]
    default_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sprites")
    out_dir = sys.argv[3] if len(sys.argv) > 3 else default_out
    os.makedirs(out_dir, exist_ok=True)

    rgb = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    # 크로마키: 초록이 다른 채널보다 얼마나 센지로 알파 계산 (가장자리는 반투명)
    greenness = g - np.maximum(r, b)
    alpha = np.clip(1 - (greenness - 30) / 70, 0, 1)
    # 초록 번짐 제거
    g = np.where(alpha < 1, np.minimum(g, np.maximum(r, b)), g)
    rgba = np.dstack([r, g, b, alpha * 255]).astype(np.uint8)

    # 캐릭터가 있는 열 구간 찾기
    solid = alpha > 0.5
    cols = solid.sum(axis=0) > 3
    segs, start = [], None
    for x, on in enumerate(list(cols) + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start > 20:  # 작은 잡티 무시
                segs.append((start, x))
            start = None

    rows = np.where(solid.sum(axis=1) > 3)[0]
    top, bottom = rows.min(), rows.max() + 1
    # 모든 프레임을 같은 크기 칸으로 잘라야 애니메이션이 흔들리지 않음
    need = max(max(e - s for s, e in segs), bottom - top) + 8
    cell = max(CELL, need)
    if need > CELL:
        print(f"경고: 캐릭터가 CELL({CELL})보다 커서 {need}로 자름 -> 다른 상태와 크기가 달라짐")

    for i, (s, e) in enumerate(segs, 1):
        cx = (s + e) // 2
        canvas = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        x0 = cx - cell // 2
        crop = Image.fromarray(rgba).crop((x0, top, x0 + cell, bottom))
        canvas.paste(crop, (0, cell - (bottom - top)))  # 바닥 정렬
        canvas = canvas.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)
        path = os.path.join(out_dir, f"{name}_{i:02d}.png")
        canvas.save(path)
        print("saved", path)


if __name__ == "__main__":
    main()
