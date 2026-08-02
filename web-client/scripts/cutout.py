"""绿幕素材抠图：软 matte 键 + 反预乘去绿边 + 木板去除。

用法：cutout.py <src> <dst> [cut|keep]
  cut （默认）去掉木板，切口沿"猫毛与木板的真实接触线"走
  keep 只去绿幕，木板保留（猫连着一块木托盘）

为什么要去掉木板：猫要卧在网页标题文字上，不能自带底座。去掉后猫身下缘
形成"卧在某物上"的观感，垂在板前的前爪与 omi 挂牌悬出，正好压住文字上沿。

素材实测（omi-perch-green.png，1024x1024）：
  绿幕      G-max(R,B) = +107~110          猫身白毛 -6 / 蓝眼 -7 / 项圈 -94
  木板正面  R-B = +76~93                   木板顶面（两端高光）R-B = +24~46
  接触处猫毛（被木板反光染红）R-B = +34~41  猫脸腮红 R-B = +44
  木板顶棱 y≈693，下沿 y≈749，接触线随爪子起伏在 y≈669~748 之间

三个已踩过的坑，判据里的每一道约束都是为它们加的：
  1. 木色阈值一旦低到 44 以下就会啃掉腮红（打出一圈白洞），所以木色判据
     必须同时限定图像下部（腮红在 y≈0.53H，木板在 y>0.6H）。
  2. 只用"颜色严判"抠木板，爪子压出阴影的那段板（R-B 掉到 30~50）会留下
     一排褐色的"牙"；只用"颜色宽判"又会连带削掉被反光染红的接触处底毛，
     削成一片半透明麻点。两者的分界靠"连通域自身色相 + 逐列深度"来判。
  3. 反预乘（减绿底）只能作用在绿幕产生的半透明像素上；贴着木板的边缘
     背景是木色，减绿会打出一圈品红脏边。
"""
import sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

src, dst = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else "cut"

rgb = np.array(Image.open(src).convert("RGB")).astype(np.float32)
R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
H, W = R.shape
yy = np.arange(H, dtype=np.float32)[:, None]

# ---------- 1) 绿幕软 matte ----------
# 不做二值化再模糊：毛尖是真半透明，用绿度线性映射成 alpha 才留得住绒毛
d = G - np.maximum(R, B)
T_LO, T_HI = 8.0, 58.0
a = np.clip((T_HI - d) / (T_HI - T_LO), 0.0, 1.0)
bg_col = np.array([np.median(rgb[..., i][d > 90]) for i in range(3)], np.float32)
print("bg green =", bg_col)

# ---------- 2) 木板 ----------
LOWER = 0.56
lower = np.broadcast_to(yy > LOWER * H, R.shape)
reddish = (R > G) & (G > B)
# 木板正面严判（起点 55 > 腮红 44，且限定下部，双重保险）
w_soft = np.clip((R - B - 55.0) / 25.0, 0, 1) * reddish * lower
BIG = H + 100

if mode != "keep":
    board_ish = (R - B > 50) & reddish & (R > 100) & lower

    # 2a) 切口高度：逐列找"木色连续段"的起点。阈值放宽到 R-B>30，把爪子
    #     阴影里的板和被反光染红的接触处底毛一起算进去。纵向连续性过滤
    #     （往下 10 行里至少 8 行木色）用来滤掉单像素噪点 —— 少了它，一个
    #     误判像素就会把整列切掉。
    warm = (R - B > 30) & reddish & lower
    csum = np.cumsum(np.vstack([np.zeros((1, W)), warm.astype(np.float32)]), 0)
    run = (csum[10:] - csum[:-10]) >= 8
    core_top = np.where(run.any(0), run.argmax(0), BIG).astype(np.float32)

    # 2b) 板两端露在绿幕下的顶面是低饱和高光（R-B 只有 24~46），颜色判据
    #     取不到，改用几何条件："上方紧邻绿幕"。猫毛压住的列上方是毛，
    #     不会误命中，所以这条只会在板两端生效。
    green = a < 0.5
    warm_lite = (R - B > 18) & reddish
    exp_top = np.full(W, BIG, np.float32)
    for x in range(W):
        t = int(core_top[x])
        if t >= BIG:
            continue
        for r in range(max(int(LOWER * H) + 3, t - 30), t + 1):
            if warm_lite[r, x] and green[r - 3, x]:
                exp_top[x] = r
                break

    cut_top = np.minimum(core_top, exp_top)
    board_top = float(exp_top.min())
    board_bot = float(np.nonzero(board_ish.any(1))[0].max())
    print("cut top=%.0f board top=%.0f bottom=%.0f exposed cols=%d" % (
        cut_top[cut_top < BIG].min(), board_top, board_bot, int((exp_top < BIG).sum())))

    # 2c) 切线整形：先 min 滤波去锯齿，再做一次带斜率代价的 min 卷积。
    #     后者把切线的高度突变拉成缓坡 —— 直接切会在外形上留一个直角
    #     台阶，在页面上看着像渲染 bug。min 只会切得更多，不会漏出木板。
    cut_top = ndimage.minimum_filter1d(cut_top, 5) - 2.0
    K, SLOPE = 70, 0.55
    cut_top = np.stack(
        [np.roll(cut_top, j) + abs(j) * SLOPE for j in range(-K, K + 1)]).min(0)
    cut_soft = np.clip(cut_top[None, :] - yy + 0.5, 0.0, 1.0)

    # 2d) 切线以下仍要保留的：垂在板前的前爪、挂在项圈下的 omi 挂牌。
    #     连通域筛选用两个判据叠加：
    #       色相 —— 白爪 R-B≈10、蓝牌 R-B<0，而板顶面碎块是 R-B>24 的木色
    #       逐列深度 —— 只保留真正垂下来的列。前爪和右侧那团后腿毛在图里
    #       本就挨着、会连成同一个连通域，若把后腿毛一起保留，它那层被
    #       反光染红的底毛就会被木色判据削成一片麻点。
    below = np.broadcast_to(yy > cut_top[None, :], R.shape)
    cand = (a > 0.6) & below & ~ndimage.binary_dilation(board_ish, iterations=2)
    seed = ndimage.binary_opening(cand, np.ones((3, 3), bool), iterations=3)
    lb, n = ndimage.label(seed, np.ones((3, 3), bool))
    deep = set(np.unique(lb[int(board_bot) + 5:, :])) - {0}
    ids = [i for i in range(1, n + 1)
           if (lb == i).sum() >= 400
           and (i in deep or np.median((R - B)[lb == i]) < 22)]
    sel = np.isin(lb, ids)
    colmax = np.where(sel.any(0), H - 1 - sel[::-1].argmax(0), -1)
    deep_col = ndimage.binary_dilation(colmax > board_top + 22, iterations=6)
    # 开运算腐蚀掉的 3px 用膨胀补回来；木板本体必须排除在保留区外，
    # 否则爪子两侧那几块木色碎屑会跟着活下来
    keep_below = ndimage.binary_dilation(sel, iterations=4) & below & deep_col[None, :]
    keep_below = (ndimage.binary_fill_holes(keep_below)
                  & ~ndimage.binary_dilation(board_ish))
    print("below-cut comps=%d kept=%s px=%d" % (n, ids, int(keep_below.sum())))

    # 爪子和挂牌是压在板上的，它们的侧边像素是和木色混出来的。保留区内
    # 另起一道更低的木色阈值硬剔（白爪 R-B≈10、蓝牌<0，伤不到），再闭运算
    # 一次：用软过渡会在挂牌下方留一小块半透明麻点，硬剔 + 闭运算才干净。
    fringe = ndimage.binary_closing(
        (R - B > 26) & reddish & keep_below, np.ones((3, 3), bool), iterations=2)
    alpha = a * np.where(keep_below, ~fringe, cut_soft) * (1 - w_soft)
else:
    keep_below = np.zeros(R.shape, bool)
    cut_top = np.full(W, BIG, np.float32)
    alpha = a.copy()

# 内部小孔（实测鼻尖高光被打出一个透明小洞）+ 孤立碎屑
holes = ndimage.binary_fill_holes(alpha > 0.5) & (alpha <= 0.5)
if holes.any():
    print("holes filled =", int(holes.sum()))
    alpha = np.where(holes, 1.0, alpha)
lb, n = ndimage.label(alpha > 0.5, np.ones((3, 3), bool))
if n > 1:
    sz = np.r_[0, ndimage.sum(np.ones_like(lb), lb, index=range(1, n + 1))]
    drop = (lb > 0) & (sz[lb] < 0.004 * R.size)
    if drop.any():
        print("dropped specks =", int(drop.sum()))
        alpha = np.where(ndimage.binary_dilation(drop, iterations=2), 0.0, alpha)
alpha = np.where(alpha < 0.03, 0.0, alpha)  # 清掉幽灵像素，保证 bbox 收紧

# ---------- 3) 反预乘：把半透明边缘里的绿底成分减掉 ----------
# 判据用绿幕 matte a 而不是最终 alpha：贴木板的边缘背景是木色，不能减绿
out = rgb.copy()
edge = (a > 0.02) & (a < 0.995)
un = (rgb - (1 - a[..., None]) * bg_col) / np.clip(a, 0.25, 1.0)[..., None]
out = np.where(edge[..., None], np.clip(un, 0, 255), out)

# ---------- 4) despill：绿色溢色压回中性（白猫的 G 本就≈(R+B)/2，几乎无损）
cap = (out[..., 0] + out[..., 2]) / 2 + 6
out[..., 1] = np.where((alpha > 0) & (out[..., 1] > cap), cap, out[..., 1])

if mode != "keep":
    # 切口上方 14 行 + 保留区：把木板反光染上的红味拉回中性，
    # 否则贴着切口会剩一道褐边
    band = ((yy > (cut_top[None, :] - 14)) & (yy <= cut_top[None, :] + 1)) | keep_below
    t = np.clip((out[..., 0] - out[..., 2] - 22) / 35, 0, 1) * 0.8 * (band & (alpha > 0))
    out[..., 0] = out[..., 0] * (1 - t) + (out[..., 1] + out[..., 2]) / 2 * t
    print("red despill px =", int((t > 0.02).sum()))

alpha_img = Image.fromarray(np.clip(alpha * 255, 0, 255).astype(np.uint8))
alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(0.4))
img = Image.fromarray(np.dstack([np.clip(out, 0, 255).astype(np.uint8),
                                 np.array(alpha_img)]))
bbox = img.split()[3].getbbox()
img = img.crop(bbox)
pad = int(max(img.size) * 0.015)
canvas = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
canvas.paste(img, (pad, pad))
canvas.save(dst)
print("saved %s size=%s bbox=%s pad=%d mode=%s" % (dst, canvas.size, bbox, pad, mode))
