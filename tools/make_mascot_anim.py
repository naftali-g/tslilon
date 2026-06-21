# -*- coding: utf-8 -*-
"""
make_mascot_anim.py — OFFLINE (not shipped). Builds the animated celebration mascot
from jumping_logo.mp4 into the project root, next to index.html:
  - mascot_anim.webp : transparent, continuously-looping animation of the bubble mascot
                       AND its grounded bounce shadow, cropped to the jump, with only the
                       cream background keyed out (the shadow is preserved and recoloured to
                       a neutral grey). Trimmed to a seamless bounce window (the source's
                       static rest frames are dropped); the wordmark/tagline are excluded
                       (they sit just below the crop). Plays in a plain <img> — no CSS
                       drop-shadow needed, the shadow is baked in.

It plays automatically in a plain <img> tag (animated WebP), so the success view
needs no <video>/JS — same as the static mascot.webp it sits beside.

Requires PyAV for mp4 decoding:  pip install av   (plus numpy / scipy / Pillow).
Run:  python3 tools/make_mascot_anim.py
"""
import os
import av
import numpy as np
from scipy import ndimage
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "jumping_logo.mp4")
OUT = os.path.join(ROOT, "mascot_anim.webp")

# Trim to the continuous-bounce window. The source has ~15 dead "at rest" frames at the start
# and ~14 settling at the end (the bubble just sits there), so looping the whole clip reads as
# "bounce ... pause ... bounce". Frames 24 (bottom of the crouch) and 47 (the landing) are
# matching bottom-contact poses, so looping between them gives a seamless, continuous bounce
# (land → compress → spring) with no rest. Keep full fps within the window.
LOOP_START = 24  # bottom of the crouch — about to spring up
LOOP_END = 47    # the landing (bottom contact); its pose matches LOOP_START for a clean seam
STRIDE = 1       # keep every Nth frame WITHIN the window — 1 = full ~24fps (smoothest)
MAXDIM = 200     # display is 124px; this is comfortably retina-crisp
QUALITY = 76
PAD = 12         # transparent breathing room around the bubble's travel

# ---- decode all frames (RGB) ----
container = av.open(SRC)
fps = float(container.streams.video[0].average_rate)
frames = np.array([f.to_ndarray(format="rgb24") for f in container.decode(video=0)])
container.close()
N, H, W, _ = frames.shape

# ---- background cream: median of all four corners across every frame ----
corners = np.concatenate([frames[:, :40, :40], frames[:, :40, -40:],
                          frames[:, -40:, :40], frames[:, -40:, -40:]], 1).reshape(-1, 3)
cream = np.median(corners, 0)

# ---- per frame (within the kept window): the bubble is the largest non-cream blob; the
#      wordmark letters are separate, smaller components, so "largest component" isolates the
#      bubble (the same trick make_assets.py uses for the alef). Fill holes so eyes/mouth stay
#      solid. ----
TEXT_TOP = 321               # the wordmark starts ~324 in the source — never frame at/below it
cream_lum = float(cream.mean())
keep = list(range(LOOP_START, min(LOOP_END, N - 1) + 1, STRIDE))
sils = {}
y0, y1, x0, x1 = H, 0, W, 0
for i in keep:
    diff = np.abs(frames[i].astype(np.int16) - cream).max(2).astype(np.float32)
    lbl, n = ndimage.label(diff > 45, np.ones((3, 3)))          # >45 = solid bubble (excludes shadow)
    sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
    sil = ndimage.binary_fill_holes(lbl == (int(np.argmax(sizes)) + 1))
    sils[i] = sil
    # Frame the crop around the bubble AND its shadow: the ground shadow drifts left and low as
    # the bubble rises, so framing on the bubble alone clips it. Include darker-than-cream pixels
    # above the wordmark; the union over all kept frames means no frame clips the shadow.
    darkness = np.clip(cream_lum - frames[i].mean(2), 0, None)
    content = sil | (darkness > 14)
    content[TEXT_TOP:, :] = False
    ys, xs = np.where(content)
    y0, y1 = min(y0, ys.min()), max(y1, ys.max())
    x0, x1 = min(x0, xs.min()), max(x1, xs.max())
y0, x0 = max(y0 - PAD, 0), max(x0 - PAD, 0)
y1, x1 = min(y1 + PAD, TEXT_TOP), min(x1 + PAD, W)

# ---- build RGBA frames as two layers ----
#   • the BUBBLE — crisp: solid silhouette + an orange-gated feathered edge (the orange gate,
#     R-B, keeps the bubble's rim but never the desaturated shadow, so the bubble stays clean).
#   • the GROUND SHADOW — preserved from the source so the bounce stays grounded: the darker-
#     than-cream pixels OUTSIDE the bubble, kept soft (capped) and recoloured to a cool grey so
#     it reads as a shadow on the white win card. The source animates it correctly (large/dark
#     at contact, small/faint at the apex), so the shadow never vanishes at max height.
SHADOW_RGB = np.array([43, 43, 54], np.float32)    # cool grey — matches the app's shadow ink
SHADOW_CAP, SHADOW_SPAN = 0.45, 165.0              # max opacity, and darkness->alpha falloff
out = []
dur = int(round(1000.0 / fps * STRIDE))
for i in keep:
    fr = frames[i].astype(np.float32)
    core = sils[i]                                              # solid bubble interior (eyes/mouth filled)
    edge = ndimage.gaussian_filter(ndimage.binary_dilation(core, iterations=1).astype(np.float32), sigma=1.0)
    orange = (fr[:, :, 0] - fr[:, :, 2]) > 55                   # bubble is orange; cream/shadow aren't
    bubble_a = np.where(core, 1.0, edge * orange)               # crisp bubble alpha
    darkness = np.clip(cream_lum - fr.mean(2), 0, None)         # how much darker than the cream ground
    not_bubble = ~ndimage.binary_dilation(core, iterations=2)
    shadow_a = np.clip(darkness / SHADOW_SPAN, 0, SHADOW_CAP) * not_bubble
    alpha = np.clip(np.maximum(bubble_a, shadow_a), 0, 1)
    rgb = np.where((shadow_a > bubble_a)[:, :, None], SHADOW_RGB, fr)   # grey where the shadow wins
    rgba = np.dstack([rgb[y0:y1, x0:x1].astype(np.uint8), (alpha[y0:y1, x0:x1] * 255).astype(np.uint8)])
    im = Image.fromarray(rgba, "RGBA")
    im.thumbnail((MAXDIM, MAXDIM), Image.LANCZOS)
    out.append(im)

# Force every frame to be a keyframe (kmin/kmax) and keep transparent RGB exact. Otherwise
# animated WebP stores frames as lossy deltas from the previous one, and the decoder accumulates
# small errors between keyframes — a shimmer that builds up over a few loops then resets. All-
# keyframes costs ~nothing here (the bubble moves too much for deltas to help) and removes it.
out[0].save(OUT, "WEBP", save_all=True, append_images=out[1:],
            duration=dur, loop=0, quality=QUALITY, method=6,
            exact=True, kmin=0, kmax=1)
print(f"  mascot_anim.webp: {round(os.path.getsize(OUT)/1024,1)} KB "
      f"({len(out)} frames @ {dur}ms, {out[0].size[0]}x{out[0].size[1]})")
