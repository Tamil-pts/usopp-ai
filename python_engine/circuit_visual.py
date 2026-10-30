"""Registered, object-aware visual evidence; never a page-sized filled highlight."""
from collections import defaultdict
from pathlib import Path
import math
import re

import numpy as np
from PIL import Image, ImageFilter


def compact(value):
    return re.sub(r'\s+', '', str(value)).casefold()


def transform_box(bounds, transform, inverse=False):
    sx, sy, dx, dy = transform
    x0, y0, x1, y1 = bounds
    values = [(x0 - dx) / sx, (y0 - dy) / sy, (x1 - dx) / sx, (y1 - dy) / sy] if inverse else [sx*x0+dx, sy*y0+dy, sx*x1+dx, sy*y1+dy]
    return [max(0, min(1, float(v))) for v in values]


def alignment(base, developed):
    """Fit only global PDF export scale/translation from distinct equal labels."""
    fa=(base.get('scene') or {}).get('frame');fb=(developed.get('scene') or {}).get('frame')
    if fa and fb:
        a,b=fa['bbox'],fb['bbox']
        sx,sy=(a[2]-a[0])/(b[2]-b[0]),(a[3]-a[1])/(b[3]-b[1])
        dx,dy=a[0]-sx*b[0],a[1]-sy*b[1]
        if abs(sx-1)<.04 and abs(sy-1)<.04 and abs(dx)<.04 and abs(dy)<.04:
            return [sx,sy,dx,dy],{'method':'matched inner drawing-frame vectors','anchors':4,'baseFrame':a,'developedFrame':b}
    groups = []
    for page in (base, developed):
        values = defaultdict(list)
        for s in page['segments']:
            if not s.get('uncertain') and len(compact(s['text'])) >= 5:
                values[compact(s['text'])].append(s)
        groups.append(values)
    anchors = []
    for name, values in groups[0].items():
        peer = groups[1].get(name, [])
        if len(values) != 1 or len(peer) != 1: continue
        centers = [((s['bbox'][0]+s['bbox'][2])/2, (s['bbox'][1]+s['bbox'][3])/2) for s in (values[0], peer[0])]
        if math.dist(*centers) < .04: anchors.append((centers[0], centers[1]))
    if len(anchors) < 5: return None, {'method': 'bounded pixel translation', 'anchors': len(anchors)}
    target, original = np.asarray([p[0] for p in anchors]), np.asarray([p[1] for p in anchors])
    keep = np.ones(len(target), dtype=bool)
    scale, shift = np.ones(2), np.median(target-original, axis=0)
    for _ in range(4):
        for axis in (0, 1):
            if np.ptp(original[keep, axis]) > .25:
                scale[axis], shift[axis] = np.polyfit(original[keep, axis], target[keep, axis], 1)
            else:
                scale[axis] = 1; shift[axis] = np.median(target[keep, axis]-original[keep, axis])
        residual = np.linalg.norm(original*scale+shift-target, axis=1)
        selected = residual < max(.0025, float(np.median(residual))*2.5)
        if selected.sum() < 5 or np.array_equal(keep, selected): break
        keep = selected
    if any(abs(scale-1) > .03) or any(abs(shift) > .03):
        return None, {'method': 'bounded pixel translation', 'anchors': len(anchors), 'notice': 'Unstable label registration was rejected.'}
    return [float(scale[0]), float(scale[1]), float(shift[0]), float(shift[1])], {
        'method': 'global scale/translation from equal source labels', 'anchors': int(keep.sum()),
        'residualPageFraction': round(float(np.median(residual[keep])), 6)}


def _paint(mask, bounds, width, height, value=True, margin=0):
    x0, y0, x1, y1 = bounds
    x0, y0 = max(0, int(x0*width)-margin), max(0, int(y0*height)-margin)
    x1, y1 = min(width, int(math.ceil(x1*width))+margin), min(height, int(math.ceil(y1*height))+margin)
    mask[y0:y1, x0:x1] = value


def _dilate(mask, size=3):
    return np.asarray(Image.fromarray(mask.astype('uint8')*255).filter(ImageFilter.MaxFilter(size))) > 0


def registered_images(base_path, developed_path, transform=None):
    with Image.open(base_path) as im: base = im.convert('RGB')
    with Image.open(developed_path) as im: developed = im.convert('RGB').resize(base.size, Image.Resampling.LANCZOS)
    width, height = base.size
    if transform is None:
        a, b = np.asarray(base.convert('L')) < 150, np.asarray(developed.convert('L')) < 150
        target = a[5:height-5:2, 5:width-5:2]
        scores = []
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                candidate = b[5-dy:height-5-dy:2, 5-dx:width-5-dx:2]
                scores.append((int((target & candidate).sum()), -(abs(dx)+abs(dy)), dx, dy))
        _, _, dx, dy = max(scores)
        transform = [1, 1, dx/width, dy/height]
    sx, sy, dx, dy = transform
    registered = developed.transform(base.size, Image.Transform.AFFINE,
        (1/sx, 0, -dx*width/sx, 0, 1/sy, -dy*height/sy), resample=Image.Resampling.BICUBIC, fillcolor='white')
    return base, registered, transform


def compare_visual(base_path, developed_path, base, developed):
    transform, registration = alignment(base, developed)
    a, b, transform = registered_images(base_path, developed_path, transform)
    width, height = a.size
    ia, ib = np.asarray(a.convert('L')) < 140, np.asarray(b.convert('L')) < 140
    # Raw mask is retained for independent verification of text-layer mismatches.
    raw_removed, raw_added = ia & ~_dilate(ib), ib & ~_dilate(ia)
    ignored = np.zeros((height, width), dtype=bool)
    # Sheet perimeter and title-block ornament are layout, not circuit objects.
    frame=(base.get('scene') or {}).get('frame')
    ignored[:int((frame['bodyTop'] if frame else .025)*height)] = True
    ignored[int((frame['footerTop'] if frame else .90)*height):] = True
    ignored[:, :int(.025*width)] = True; ignored[:, int(.975*width):] = True
    for page, tr in [(base, None), (developed, transform)]:
        for table in page.get('tables',[]):
            _paint(ignored,transform_box(table['bbox'],tr) if tr else table['bbox'],width,height,margin=3)
        for segment in page['segments']:
            bounds = transform_box(segment['bbox'], tr) if tr else segment['bbox']
            _paint(ignored, bounds, width, height, margin=3)
    # Compare photos by their own registered image objects. Never hide an entire
    # scanned schematic merely because one changed wire is a small pixel ratio.
    equal_photos = 0
    for image in base.get('images', []):
        bounds = image['bbox']; area = (bounds[2]-bounds[0])*(bounds[3]-bounds[1])
        if area > .2: continue
        peers = [i for i in developed.get('images', []) for t in [transform_box(i['bbox'], transform)] if math.dist(
            [(bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2],
            [(t[0]+t[2])/2, (t[1]+t[3])/2]) < .02]
        if not peers: continue
        crop = (int(bounds[0]*width), int(bounds[1]*height), int(bounds[2]*width), int(bounds[3]*height))
        pa = np.asarray(a.crop(crop).resize((64,64)), dtype=float)/255
        pb = np.asarray(b.crop(crop).resize((64,64)), dtype=float)/255
        error = float(np.mean(np.abs(pa-pb)))
        if error < .045:
            _paint(ignored, bounds, width, height, margin=4); equal_photos += 1
    removed, added = raw_removed & ~ignored, raw_added & ~ignored
    combined = added | removed
    # Small tiles and component splitting prevent a frame/long network from
    # becoming one page-sized rectangle. The colored mask marks actual pixels.
    tile = 6
    padded = np.pad(combined, ((0,(-height)%tile),(0,(-width)%tile)))
    grid = padded.reshape(padded.shape[0]//tile,tile,padded.shape[1]//tile,tile).sum(axis=(1,3)) >= 3
    pending = set(map(tuple,np.argwhere(grid))); regions = []
    while pending:
        seed = min(pending); pending.remove(seed); stack = [seed]; cells = [seed]
        while stack:
            y,x = stack.pop()
            for oy,ox in ((-1,0),(1,0),(0,-1),(0,1)):
                point = y+oy,x+ox
                if point in pending: pending.remove(point); stack.append(point); cells.append(point)
        groups = [cells]
        ys,xs = zip(*cells)
        if (max(xs)-min(xs)+1)*tile*(max(ys)-min(ys)+1)*tile/(width*height) > .08:
            buckets = defaultdict(list)
            for y,x in cells: buckets[(y//16,x//16)].append((y,x))
            groups = list(buckets.values())
        for group in groups:
            ys,xs = zip(*group)
            x0,y0,x1,y1 = max(0,min(xs)*tile-2),max(0,min(ys)*tile-2),min(width,(max(xs)+1)*tile+2),min(height,(max(ys)+1)*tile+2)
            na,nr = int(added[y0:y1,x0:x1].sum()),int(removed[y0:y1,x0:x1].sum())
            if na+nr < 18: continue
            bounds = [x0/width,y0/height,x1/width,y1/height]
            regions.append({'bbox': bounds,'developedBox': transform_box(bounds,transform,inverse=True),'addedPixels':na,'removedPixels':nr})
    colored = np.asarray(a).copy()
    colored[_dilate(removed)] = [225,60,76]; colored[_dilate(added)] = [0,154,104]
    stats = {'addedPixels':int(added.sum()),'removedPixels':int(removed.sum()),'ignoredRenderPixels':int(((raw_added|raw_removed)&ignored).sum()),
             'equivalentPhotos':equal_photos,'structuredTableMasks':len(base.get('tables',[]))+len(developed.get('tables',[])),
             'registration':{**registration,'transform':transform},
             'method':'registered text/object masks with local raster residuals'}
    return regions,Image.fromarray(colored),stats,{'added':raw_added,'removed':raw_removed,'transform':transform,'size':(width,height)}


def visible_text_change(change, evidence):
    """Text extraction differences need visible support; uncertain glyphs are separate checks."""
    width,height = evidence['size']; boxes = []
    if change.get('before'): boxes.append(change['before']['bbox'])
    if change.get('after'): boxes.append(transform_box(change['after']['bbox'], evidence['transform']))
    if not boxes: return False
    bounds = [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    mask = np.zeros((height,width),dtype=bool); _paint(mask,bounds,width,height,margin=2)
    count = int(((evidence['added']|evidence['removed'])&mask).sum())
    return count >= 6
