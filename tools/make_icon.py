"""sprites/idle_01.png(또는 icon.png)로 exe 아이콘(build/icon.ico) 만들기"""
import os
import sys

from PIL import Image

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = next((p for p in (os.path.join(root, "icon.png"), os.path.join(root, "sprites", "idle_01.png"))
            if os.path.exists(p)), None)
if src is None:
    sys.exit(0)                                         # 그림이 없으면 기본 아이콘
img = Image.open(src).convert("RGBA")
img = img.crop(img.getbbox())                           # 투명 여백 잘라서 아이콘을 꽉 차게
side = max(img.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
os.makedirs(os.path.join(root, "build"), exist_ok=True)
square.save(os.path.join(root, "build", "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("아이콘: build/icon.ico")
