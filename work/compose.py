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

# 2b. edge colour decontamination: every anti-aliased boundary pixel takes the
# colour of the nearest well-inside pixel, so no wall colour bleeds into edges
from scipy import ndimage
solid = a > 250
core = cv2.erode(solid.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
if not core.any():
    core = solid if solid.any() else a > a.max() - 1
_, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
edge = (a > 0) & (~core)
rgb[edge] = rgb[iy[edge], ix[edge]]

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
prgb += np.random.normal(0, 2.2, prgb.shape)
pn = Image.fromarray(np.clip(prgb, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.35))
pn.putalpha(person.split()[3])
person = pn

bg = Image.open(BG).convert('RGB')
W, BGH = bg.size
cx, feet_y = 853, 1248
px = cx - person.width // 2
py = feet_y - person.height

# 5. soft shadow on wall behind
sh = person.split()[3].point(lambda v: int(v * 0.10))
sh = sh.filter(ImageFilter.GaussianBlur(24))
full_sh = Image.new('L', bg.size, 0)
full_sh.paste(sh, (px + 12, py + 20))
shadow_layer = Image.new('RGB', bg.size, (25, 22, 20))
tmp = bg.copy()
tmp.paste(shadow_layer, (0, 0), full_sh)
bg = tmp

# 6. floor contact shadow (tight anchor + soft spread)
tight = person.split()[3].point(lambda v: int(v * 0.5))
tight = tight.crop((0, person.height - 70, person.width, person.height))
tight = tight.filter(ImageFilter.MaxFilter(5))
tight = tight.filter(ImageFilter.GaussianBlur(2.5))
tight_full = Image.new('L', bg.size, 0)
tight_full.paste(tight, (px, py + person.height - 70))

soft = Image.new('L', bg.size, 0)
d = ImageDraw.Draw(soft)
d.ellipse([cx - 200, feet_y - 34, cx + 200, feet_y + 36], fill=110)
d.ellipse([cx - 140, feet_y - 24, cx + 140, feet_y + 26], fill=165)
soft = soft.filter(ImageFilter.GaussianBlur(13))

fs = ImageChops.lighter(tight_full, soft)
fs_layer = Image.new('RGB', bg.size, (30, 26, 24))
tmp = bg.copy()
tmp.paste(fs_layer, (0, 0), fs)
bg = tmp

# 7. paste person
bg.paste(person, (px, py), person)

bg.save(OUT, quality=95, subsampling=0)
print('saved', OUT, bg.size, 'person box', (px, py, px + person.width, py + person.height))
