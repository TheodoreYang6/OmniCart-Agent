"""品牌素材构建：卧姿主视觉 + apple-touch-icon。

用法：build_brand_assets.py <cutout 输出的 png> <public 目录>
- brand/omi-perch.png：抠好的卧姿猫，缩到 640px 宽（渲染最大 ~280px，够 2x），无损优化
- apple-touch-icon.png：180x180，品牌渐变圆角底 + 猫头（iOS 不支持透明，必须给底色）
"""
import sys
import numpy as np
from PIL import Image, ImageDraw

src = sys.argv[1]
out_dir = sys.argv[2]

im = Image.open(src).convert("RGBA")

# ---- 1) 主视觉：等比缩到 640 宽 ----
target_w = 640
perch = im.resize((target_w, round(im.height * target_w / im.width)), Image.LANCZOS)
perch.save(f"{out_dir}/brand/omi-perch.png", optimize=True)
print(f"brand/omi-perch.png {perch.size}")

# App-icon assets are now maintained from public/brand/omi-ai-icon.svg. Do not
# regenerate apple-touch-icon or favicon from the mascot cutout: doing so would
# silently restore the previous 3D-cat branding.
print("Skipped Apple/favicon generation; use the shared AI-line icon.")
raise SystemExit(0)

# ---- 2) apple-touch-icon：截猫头 + 品牌渐变底 ----
# 头部框用比例常量（对 omi-perch 素材实测）：猫身向右下逐行延展
# （y=100 行右界 522 → y=420 行 804），因此不能用整图/上半区的 alpha bbox，
# 否则框会被身体拉宽，猫头偏出图标（已实拍验证过两次）。
# 比例随 cutout 的裁切框变化：换素材/改抠图流程后要按新 bbox 重算。
W, Hh = im.width, im.height
hx0, hx1 = int(W * 0.075), int(W * 0.748)
hy0, hy1 = 0, int(Hh * 0.72)
cx, cy = (hx0 + hx1) // 2, (hy0 + hy1) // 2
side = max(hx1 - hx0, hy1 - hy0)
box = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
head = im.crop(box)  # 越界部分自动为透明，保证正方形且猫头居中

ICON = 180
inner = int(ICON * 0.92)
head = head.resize((inner, round(head.height * inner / head.width)), Image.LANCZOS)

# 品牌渐变底（#256BFF -> #4D8BFF -> #7DD3FC，与 .gradient-brand 同源）
grad = Image.new("RGB", (ICON, ICON))
stops = [(0.0, (0x25, 0x6B, 0xFF)), (0.55, (0x4D, 0x8B, 0xFF)), (1.0, (0x7D, 0xD3, 0xFC))]
px = grad.load()
for y in range(ICON):
    for x in range(ICON):
        t = (x / ICON * 0.5 + y / ICON * 0.5)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                px[x, y] = tuple(round(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
                break
        else:
            px[x, y] = stops[-1][1]

icon = grad.convert("RGBA")
mask = Image.new("L", (ICON, ICON), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, ICON - 1, ICON - 1], radius=int(ICON * 0.22), fill=255)
icon.putalpha(mask)
# 猫头居中（水平居中，垂直略下以平衡耳朵的视觉重量）
icon.alpha_composite(head, ((ICON - head.width) // 2, int((ICON - head.height) * 0.5)))
icon.save(f"{out_dir}/apple-touch-icon.png", optimize=True)
print(f"apple-touch-icon.png {icon.size} head_box={box}")

# ---- 3) favicon.ico（32/16 双尺寸，老浏览器后备）----
icon.convert("RGB").resize((64, 64), Image.LANCZOS).save(
    f"{out_dir}/favicon.ico", sizes=[(32, 32), (16, 16)]
)
print("favicon.ico saved")
