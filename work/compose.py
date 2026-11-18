from PIL import Image, ImageDraw, ImageFilter, ImageChops
import numpy as np, cv2

PERSON = '/workspace/.uploads/8cce3cab-e6e8-4879-87cc-c5207d871e22_微信图片_20261118093751_11_172.jpg'
BG = '/workspace/.uploads/3a051c09-977e-43ee-a270-9707b552253c_微信图片_20261118091419_205_120.jpg'
CUT = '/workspace/work/p_u2net.png'
OUT = '/workspace/人物手持营业执照_门头照.jpg'

# person cutout
cut = Image.open(CUT).convert('RGBA')
rgb = np.array(cut.convert('RGB')).astype(np.float32)
a = np.array(cut)[:, :, 3]

# 1. remove background leaked between legs
mask = np.zeros(a.shape, np.uint8)
poly = np.array([[603, 1244], [637, 1244], [643, 1502], [611, 1502]], np.int32)
cv2.fillPoly(mask, [poly], 255)
mask = cv2.GaussianBlur(mask, (0, 0), 1.6)
a = (a.astype(np.float32) * (1 - mask / 255.0)).astype(np.uint8)

# 2. white balance / brightness match to the office wall
# person wall (210,200,189) -> target (172,168,166)
gains = np.array([172 / 210.4, 168 / 200.4, 166 / 188.6], np.float32)
rgb *= gains
np.clip(rgb, 0, 255, out=rgb)

# 2b. edge colour decontamination: unpremultiply the original beige wall out of every
# anti-aliased boundary pixel so the matte edge keeps the subject's own colour
alpha_f = a.astype(np.float32) / 255.0
wall_bg = np.array([172.0, 168.0, 166.0], np.float32)
fg = np.where(
    alpha_f[..., None] > 0.06,
    (rgb - wall_bg * (1 - alpha_f[..., None])) / np.clip(alpha_f[..., None], 0.06, 1),
    rgb,
)
rgb = np.clip(fg, 0, 255)

# 3. erode edge slightly to remove background fringe, then feather
alpha = Image.fromarray(a).filter(ImageFilter.MinFilter(5))
alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))

# darken the very bottom rows of the cutout (shoe soles) so no floor colour rim shows
anp = np.array(alpha)
solid_rows = np.where(anp.any(1))[0]
bot = solid_rows.max()
rgb[bot - 7:bot + 1][anp[bot - 7:bot + 1] > 0] *= 0.45

# neutralise the patch of the old wooden floor still visible between the ankles
pm = np.zeros(a.shape, np.uint8)
cv2.ellipse(pm, (629, 1528), (36, 44), 0, 0, 360, 255, -1)
pm = cv2.GaussianBlur(pm, (0, 0), 6).astype(np.float32)[..., None] / 255.0
lum = rgb.mean(2, keepdims=True)
rgb = rgb * (1 - pm) + (lum * 0.42) * pm

person = Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).convert('RGBA')
person.putalpha(alpha)

# crop to content
bbox = person.getbbox()
person = person.crop(bbox)

# 4. scale & position
H = 700
scale = H / person.height
person = person.resize((round(person.width * scale), H), Image.LANCZOS)
# very slight softening + sensor noise to sit in the same optical conditions as the room photo
prgb = np.array(person.convert('RGB')).astype(np.float32)
# ambient falloff: ceiling light makes the upper body brighter than the shoes
yy = np.arange(H, dtype=np.float32)[:, None, None] / H
prgb *= 1.0 - 0.10 * yy ** 1.6
prgb[..., 0] *= 0.99
prgb[..., 2] *= 1.01
# atmospheric wash from the dim room lifts the blacks and lowers contrast
prgb = prgb * 0.965 + np.array([163, 158, 155], np.float32) * 0.035
prgb += np.random.normal(0, 1.8, prgb.shape)
pn = Image.fromarray(np.clip(prgb, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.3))
pn.putalpha(person.split()[3])
person = pn

bg = Image.open(BG).convert('RGB')
W, BGH = bg.size
cx, feet_y = 853, 1256
px = cx - person.width // 2
py = feet_y - person.height

# 5. soft shadow on wall behind (multiplicative so the wall gradient stays intact)
sh = person.split()[3].point(lambda v: int(v * 0.5))
sh = sh.filter(ImageFilter.GaussianBlur(26))
full_sh = Image.new('L', bg.size, 0)
full_sh.paste(sh, (px + 14, py + 24))
m = (np.array(full_sh).astype(np.float32) / 255.0 * 0.16)[..., None]
bg = Image.fromarray(np.clip(np.array(bg).astype(np.float32) * (1 - m), 0, 255).astype(np.uint8))

# 5b. faint reflection of the legs/shoes on the glossy floor
refl_h = 90
ref = person.crop((0, person.height - refl_h, person.width, person.height)).transpose(Image.FLIP_TOP_BOTTOM)
ga = np.linspace(1, 0, ref.height, dtype=np.float32)[:, None] ** 1.4
ra = np.array(ref.split()[3]).astype(np.float32) * ga * 0.24
ref.putalpha(Image.fromarray(ra.astype(np.uint8)))
ref = ref.filter(ImageFilter.GaussianBlur(4))
tmp = bg.copy()
tmp.paste(ref, (px, feet_y), ref)
bg = tmp

# 6. floor contact shadow (tight anchor + soft spread)
tight = person.split()[3].point(lambda v: int(v * 0.75))
tight = tight.crop((0, person.height - 70, person.width, person.height))
tight = tight.filter(ImageFilter.GaussianBlur(5))
tight_full = Image.new('L', bg.size, 0)
tight_full.paste(tight, (px, py + person.height - 70 + 4))

soft = Image.new('L', bg.size, 0)
d = ImageDraw.Draw(soft)
d.ellipse([cx - 150, feet_y - 28, cx + 150, feet_y + 30], fill=90)
d.ellipse([cx - 110, feet_y - 20, cx + 110, feet_y + 22], fill=150)
soft = soft.filter(ImageFilter.GaussianBlur(9))

contact = Image.new('L', bg.size, 0)
d = ImageDraw.Draw(contact)
d.ellipse([cx - 135, feet_y - 12, cx + 135, feet_y + 14], fill=215)
contact = contact.filter(ImageFilter.GaussianBlur(4))

fs = ImageChops.lighter(ImageChops.lighter(tight_full, soft), contact)
m = (np.array(fs).astype(np.float32) / 255.0 * 0.72)[..., None]
bg = Image.fromarray(np.clip(np.array(bg).astype(np.float32) * (1 - m), 0, 255).astype(np.uint8))

# 6b. light wrap: let the room colour bleed onto the silhouette edge so the cut-out
# does not read as a sticker pasted on top of the scene
bgb = bg.filter(ImageFilter.GaussianBlur(14))
pa = np.array(person.split()[3]).astype(np.float32) / 255.0
band = pa - cv2.erode((pa * 255).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(np.float32) / 255.0
band = cv2.GaussianBlur(band, (0, 0), 1.2)[..., None] * 0.35
# no light wrap on the shoes / floor contact, otherwise the soles pick up a bright halo
ramp = np.clip((np.arange(person.height, dtype=np.float32) - (person.height * 0.63)) / 45.0, 0, 1)[:, None, None]
band = band * (1 - ramp)
p_rgb = np.array(person.convert('RGB')).astype(np.float32)
b_rgb = np.array(bgb.crop((px, py, px + person.width, py + person.height))).astype(np.float32)
p_rgb = p_rgb * (1 - band) + b_rgb * band
person = Image.fromarray(np.clip(p_rgb, 0, 255).astype(np.uint8)).convert('RGBA')
person.putalpha(Image.fromarray((pa * 255).astype(np.uint8)))

# 6c. window rim light: cool daylight from the left corridor catches the left contour
pa2 = np.array(person.split()[3]).astype(np.float32) / 255.0
er2 = cv2.erode((pa2 * 255).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(np.float32) / 255.0
rim = np.clip(pa2 - er2, 0, 1)
rim = cv2.GaussianBlur(rim, (0, 0), 2.2)
h2, w2 = pa2.shape
xs = (np.arange(w2, dtype=np.float32)[None, :] / w2)
side = np.clip(1.0 - xs / 0.32, 0, 1) ** 1.6
ys = np.clip((np.arange(h2, dtype=np.float32)[:, None] - 40) / 90.0, 0, 1)
ys *= np.clip(((h2 - 105) - np.arange(h2, dtype=np.float32)[:, None]) / 60.0, 0, 1)
rim = (rim * side * ys * 0.6)[..., None]
wash = (side * ys * pa2 * 0.06)[..., None]
day = np.array([206, 220, 236], np.float32)
q = np.array(person.convert('RGB')).astype(np.float32)
q = q * (1 - rim) + day * rim
q = q * (1 + wash)
person = Image.fromarray(np.clip(q, 0, 255).astype(np.uint8)).convert('RGBA')
person.putalpha(Image.fromarray((pa * 255).astype(np.uint8)))

# 6d. the matte bridged the gap between the legs with the old background: clear that strip
# so the office shows through instead of a grey slab
pr = np.array(person.convert('RGB')).astype(np.float32)
pf = np.array(person.split()[3])
h4, w4 = pf.shape
y0, y1 = int(h4 * 0.62), h4
lumf = pr.mean(2)
lk = np.zeros((h4, w4), np.uint8)
xl, xr = int(w4 * 0.34), int(w4 * 0.66)
for yy in range(y0, y1):
    row = lumf[yy]
    med = np.median(row[xl:xr])
    lk[yy, xl:xr] = (row[xl:xr] > med + 42).astype(np.uint8) * 255
lk = cv2.morphologyEx(lk, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
lk = cv2.dilate(lk, np.ones((5, 5), np.uint8))
pf[y0:y1][lk[y0:y1] > 0] = 0
# pull the leg silhouette 2px into the opening with a dark inner-fabric edge, so the slit
# is narrower and has a shadowed rim instead of a clean cut against the bright wall
ring = cv2.dilate(lk, np.ones((5, 5), np.uint8)) - lk
edge_col = np.array([26, 26, 30], np.float32)
sele = ring[y0:y1] > 0
pr_band = pr[y0:y1]
pr_band[sele] = edge_col
pf[y0:y1][sele] = 255
pr[y0:y1] = pr_band
person = Image.fromarray(np.clip(pr, 0, 255).astype(np.uint8)).convert('RGBA')
person.putalpha(Image.fromarray(pf))
# cut the bright wall fringe left along the opening: it reads as a glass-tube highlight
pa_np = pf > 0
g0 = np.zeros_like(pa_np)
for yy in range(y0, h4):
    cs = np.where(pa_np[yy])[0]
    if cs.size > 1:
        lo_, hi_ = cs.min(), cs.max()
        sgm = pa_np[yy, lo_:hi_ + 1]
        g0[yy, lo_ + 1:hi_] = ~sgm[1:-1]
ring0 = cv2.dilate((g0 * 255).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
ring0 &= ~g0
pf[ring0 & (pf < 250)] = 0
# feather the inner-leg edge so the opening is not a razor-sharp slot
fe = cv2.GaussianBlur(pf[int(h4*0.60):int(h4*0.93)].astype(np.float32), (0, 0), 0.9)
pf[int(h4*0.60):int(h4*0.93)] = fe.astype(np.uint8)
person.putalpha(Image.fromarray(pf))

# 7. paste person
# harden the shoe soles so the contact edge stays crisp instead of fading into the floor
pa_img = person.split()[3]
pav = np.array(pa_img)
s0 = max(0, person.height - 55)
sub = pav[s0:]
sub[sub >= 140] = 255
sub[sub < 140] = 0
person.putalpha(Image.fromarray(pav))

bg.paste(person, (px, py), person)

# 8. inner-leg gap: dim what shows through between the legs and close the top of the slit,
# otherwise the bright slit reads as a cut-out seam instead of two legs standing apart
pa3 = np.array(person.split()[3]) > 0
h3, w3 = pa3.shape
gap = np.zeros((h3, w3), np.uint8)
g_start = int(h3 * 0.60)
for yy in range(g_start, h3):
    cols = np.where(pa3[yy])[0]
    if cols.size > 1:
        lo, hi = cols.min(), cols.max()
        seg = pa3[yy, lo:hi + 1]
        gap[yy, lo + 1:hi] = (~seg[1:-1]).astype(np.uint8)
gap = cv2.dilate(gap, np.ones((3, 3), np.uint8))
gap_img = Image.fromarray(gap * 255).filter(ImageFilter.GaussianBlur(2.4))
gap_full = Image.new('L', bg.size, 0)
gap_full.paste(gap_img, (px, py))
grows = np.where(gap.any(1))[0]
wide = np.where(gap.sum(1) >= 8)[0]
gy0 = py + (int(wide.min()) if wide.size else int(grows.min()) if grows.size else g_start)
t = np.clip((np.arange(bg.size[1], dtype=np.float32) - gy0) / max(1.0, person.height * 0.155), 0, 1)[:, None, None]
# the room behind the legs is metres away: give it a shallow depth-of-field so the
# opening stops reading as a crisp slot
bg = Image.composite(bg.filter(ImageFilter.GaussianBlur(3.6)), bg, gap_full)
gv = np.array(gap_full).astype(np.float32)[..., None] / 255.0
occl = gv * (0.76 - 0.06 * t)
bg = Image.fromarray(np.clip(np.array(bg).astype(np.float32) * (1 - occl), 0, 255).astype(np.uint8))

bg.save(OUT, quality=95, subsampling=0)
print('saved', OUT, bg.size, 'person box', (px, py, px + person.width, py + person.height))
