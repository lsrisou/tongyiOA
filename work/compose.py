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
ramp = np.clip((np.arange(person.height, dtype=np.float32) - (person.height - 110)) / 60.0, 0, 1)[:, None, None]
band = band * (1 - ramp)
p_rgb = np.array(person.convert('RGB')).astype(np.float32)
b_rgb = np.array(bgb.crop((px, py, px + person.width, py + person.height))).astype(np.float32)
p_rgb = p_rgb * (1 - band) + b_rgb * band
person = Image.fromarray(np.clip(p_rgb, 0, 255).astype(np.uint8)).convert('RGBA')
person.putalpha(Image.fromarray((pa * 255).astype(np.uint8)))

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

bg.save(OUT, quality=95, subsampling=0)
print('saved', OUT, bg.size, 'person box', (px, py, px + person.width, py + person.height))
