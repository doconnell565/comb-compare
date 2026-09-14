#!/usr/bin/env python
"""Generate STEP files for a pinned music box cylinder and its pinning tooling.

Reads tools/params.json and a pin map CSV exported by Comb Compare, and writes:

  out/cylinder.step     brass cylinder, bore, radial blind holes for every pin, index notch
  out/punch.step        height-stop pin setting punch (drill rod)
  out/jig_plate.step    pin length jig plate (thickness = pin length)
  out/jig_base.step     base plate for the jig
  out/cradle.step       two-upright cradle that holds the cylinder by its arbor
  out/SUMMARY.md        dimensions, masses, hole count and drawing callouts for the shop

Usage:  .venv/bin/python tools/make_step.py [tools/params.json]
"""
import csv, json, math, os, sys
import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
params_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "params.json")
with open(params_path) as f:
    P = json.load(f)
OUT = os.path.join(os.path.dirname(params_path), "out")
os.makedirs(OUT, exist_ok=True)

C, PIN, PU, J, CR = P["cylinder"], P["pin"], P["punch"], P["jig"], P["cradle"]
R = C["diameter"] / 2.0

# ---------------------------------------------------------------- pin map
csv_path = P["pin_map_csv"]
if not os.path.isabs(csv_path):
    csv_path = os.path.join(os.path.dirname(params_path), csv_path)
pins = []
with open(csv_path, newline="") as f:
    for row in csv.reader(f):
        if not row or row[0].startswith("#"):
            continue
        if row[0] == "pin":
            continue
        try:
            n, t, tooth, note, folded, angle, axial, arc = row[:8]
            pins.append({"n": int(n), "t": float(t), "tooth": int(tooth), "note": note, "angle": float(angle)})
        except ValueError:
            continue  # thinned/dropped sections have a different shape
if not pins:
    sys.exit("no pins read from " + csv_path)
teeth_used = sorted({p["tooth"] for p in pins})
if teeth_used[-1] > C["tooth_count"]:
    sys.exit(f"pin map uses tooth {teeth_used[-1]} but tooth_count is {C['tooth_count']}")
row_span = (C["tooth_count"] - 1) * C["tooth_pitch"]
if C["first_row_offset"] + row_span > C["length"] - 1.0:
    sys.exit("tooth rows do not fit on the cylinder length; check first_row_offset, tooth_pitch, length")

def z_of(tooth):
    return C["first_row_offset"] + (tooth - 1) * C["tooth_pitch"]

# ---------------------------------------------------------------- cylinder
def make_cylinder():
    body = cq.Workplane("XY").circle(R).extrude(C["length"])
    if C["bore_diameter"] > 0:
        depth = C["length"] if C["bore_through"] else C["length"] * 0.5
        bore = cq.Workplane("XY").circle(C["bore_diameter"] / 2).extrude(depth)
        body = body.cut(bore)
    if C["end_chamfer"] > 0:
        try:
            body = body.faces(">Z or <Z").edges(cq.selectors.RadiusNthSelector(-1)).chamfer(C["end_chamfer"])
        except Exception as e:  # chamfer is cosmetic; do not fail the part over it
            print("end chamfer skipped:", e)

    hd, depth, ch = C["hole_diameter"], C["hole_depth"], C["hole_chamfer"]
    # one tool per pin: blind hole plus entry chamfer cone, fused, then cut one at a time so the result stays a single solid
    hole0 = cq.Solid.makeCylinder(hd / 2, depth + 0.5, cq.Vector(R - depth, 0, 0), cq.Vector(1, 0, 0))
    if ch > 0:
        cone0 = cq.Solid.makeCone(hd / 2, hd / 2 + ch + 0.3, ch + 0.3, cq.Vector(R - ch, 0, 0), cq.Vector(1, 0, 0))
        tool0 = hole0.fuse(cone0).clean()
    else:
        tool0 = hole0
    def hole_present(solid, angle, z):
        th = math.radians(angle)
        probe = cq.Vector((R - depth * 0.5) * math.cos(th), (R - depth * 0.5) * math.sin(th), z)
        return not solid.isInside(probe, 1e-4)
    for p in pins:
        z = z_of(p["tooth"])
        # the OCC boolean occasionally fails silently on one tool; verify each hole and retry with a hair of rotation
        for nudge in (0.0, 0.02, -0.02, 0.05):
            tool = tool0.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), p["angle"] + nudge).translate(cq.Vector(0, 0, z))
            trial = body.cut(tool)
            if len(trial.solids().vals()) == 1 and hole_present(trial.val(), p["angle"], z):
                body = trial
                if nudge:
                    print(f"pin {p['n']} needed a {nudge} deg nudge to cut")
                break
        else:
            sys.exit(f"could not cut the hole for pin {p['n']} at {p['angle']} deg, tooth {p['tooth']}")
    n_solids = len(body.solids().vals())
    if n_solids != 1:
        sys.exit(f"cylinder boolean produced {n_solids} solids; expected 1")

    # index notch at angle 0 on the z=0 end: the tune start and the shop's angular datum
    nw, nd = C["index_notch_width"], C["index_notch_depth"]
    if nw > 0 and nd > 0:
        notch = cq.Workplane("XY").box(nd * 2, nw, 2.0, centered=(True, True, False)).translate((R, 0, 0))
        body = body.cut(notch)
    return body

# ---------------------------------------------------------------- punch
def make_punch():
    body = cq.Workplane("XY").circle(PU["body_diameter"] / 2).extrude(PU["length"] - PU["tip_length"])
    tip = cq.Workplane("XY").workplane(offset=PU["length"] - PU["tip_length"]).circle(PU["tip_diameter"] / 2).extrude(PU["tip_length"])
    body = body.union(tip)
    # concave face matching the cylinder: a groove of radius R across the tip, its edges at the tip face and its
    # centre recessed by the sag of that arc over the tip width, so the punch seats on the barrel's crest
    half_tip = PU["tip_diameter"] / 2
    sag = R - math.sqrt(R * R - half_tip * half_tip)
    saddle = cq.Solid.makeCylinder(R, PU["tip_diameter"] * 2, cq.Vector(0, -PU["tip_diameter"], PU["length"] - sag + R), cq.Vector(0, 1, 0))
    body = body.cut(saddle)
    # the height-stop bore: pin diameter plus clearance, depth = standoff below the deepest point of the groove
    bore_d = PIN["diameter"] + PU["bore_clearance"]
    bore = cq.Solid.makeCylinder(bore_d / 2, PIN["standoff"] + R + 1, cq.Vector(0, 0, PU["length"] - sag - PIN["standoff"]), cq.Vector(0, 0, 1))
    body = body.cut(bore)
    if PU.get("shank_flat"):
        flat = cq.Workplane("XY").box(PU["body_diameter"], PU["body_diameter"], 12, centered=(True, True, False)).translate((PU["body_diameter"] * 0.5 + PU["body_diameter"] * 0.4, 0, 4))
        body = body.cut(flat)
    return body

# ---------------------------------------------------------------- jig
def make_jig_plate():
    t = PIN["length"]
    plate = cq.Workplane("XY").box(J["plate_length"], J["plate_width"], t, centered=(True, True, False))
    hd = PIN["diameter"] + J["hole_clearance"]
    xs = [(i - (J["hole_count"] - 1) / 2) * J["hole_pitch"] for i in range(J["hole_count"])]
    plate = plate.faces(">Z").workplane().pushPoints([(x, 0) for x in xs]).hole(hd)
    dx = J["plate_length"] / 2 - 4
    plate = plate.faces(">Z").workplane().pushPoints([(-dx, 0), (dx, 0)]).hole(J["dowel_diameter"])
    return plate

def make_jig_base():
    base = cq.Workplane("XY").box(J["plate_length"], J["plate_width"], J["base_thickness"], centered=(True, True, False))
    dx = J["plate_length"] / 2 - 4
    base = base.faces(">Z").workplane().pushPoints([(-dx, 0), (dx, 0)]).hole(J["dowel_diameter"] - 0.02, depth=J["base_thickness"] - 1.5)
    return base

# ---------------------------------------------------------------- cradle
def make_cradle():
    L, W, H = CR["length"], CR["width"], CR["height"]
    base = cq.Workplane("XY").box(L, W, 6, centered=(True, True, False))
    up_t = 8.0
    ux = L / 2 - up_t / 2
    uprights = (cq.Workplane("XY").pushPoints([(-ux, 0), (ux, 0)]).box(up_t, W, H - 6, centered=(True, True, False)).translate((0, 0, 6)))
    body = base.union(uprights)
    # V notch for the arbor in each upright, open at the top; the cylinder body hangs between the uprights
    half = math.radians(CR["v_angle_deg"] / 2)
    vd = W * 0.45
    vw = vd * math.tan(half)
    v = (cq.Workplane("YZ").polyline([(-vw, H + 0.01), (0, H - vd), (vw, H + 0.01)]).close().extrude(L + 2, both=True))
    body = body.cut(v)
    return body

# ---------------------------------------------------------------- build + export
parts = {
    "cylinder": (make_cylinder, "brass C360", 8.5),
    "punch": (make_punch, "O1 drill rod, harden and temper", 7.85),
    "jig_plate": (make_jig_plate, "O1 tool steel, hardened, faces ground parallel", 7.85),
    "jig_base": (make_jig_base, "mild steel or aluminium", 7.85),
    "cradle": (make_cradle, "aluminium (or wood, not worth machining)", 2.7),
}
summary = []
for name, (fn, material, density) in parts.items():
    obj = fn()
    path = os.path.join(OUT, name + ".step")
    cq.exporters.export(obj, path)
    solid = obj.val()
    bb = solid.BoundingBox()
    vol = solid.Volume()
    summary.append((name, material, bb, vol, vol * density / 1000.0, path))
    print(f"{name:10s} {os.path.getsize(path)/1024:7.1f} KB  {bb.xlen:6.2f} x {bb.ylen:6.2f} x {bb.zlen:6.2f} mm  {vol*density/1000:6.1f} g")

# ---------------------------------------------------------------- summary for the shop
mm = lambda v: f"{v:.2f}"
lines = [
    "# Cylinder and tooling, shop summary", "",
    f"Generated from `{os.path.basename(csv_path)}` with `{os.path.basename(params_path)}`. All dimensions mm.", "",
    "## Parts", "", "| Part | Material | Envelope | Mass |", "|---|---|---|---|",
]
for name, material, bb, vol, mass, path in summary:
    lines.append(f"| {name} | {material} | {mm(bb.xlen)} x {mm(bb.ylen)} x {mm(bb.zlen)} | {mass:.1f} g |")
lines += [
    "", "## Cylinder callouts", "",
    f"- Outside diameter {mm(C['diameter'])}, length {mm(C['length'])}, bore {mm(C['bore_diameter'])} {'through' if C['bore_through'] else 'blind'}.",
    f"- {len(pins)} radial blind holes, diameter {mm(C['hole_diameter'])} +0.02/-0, depth {mm(C['hole_depth'])} +0.2/-0 from the surface, entry chamfer {mm(C['hole_chamfer'])} x 45 deg.",
    f"- Hole rows on {mm(C['tooth_pitch'])} pitch, first row {mm(C['first_row_offset'])} from the Z=0 end, {C['tooth_count']} rows possible, {len(teeth_used)} used. Row position tolerance +/-0.03.",
    f"- Angular positions listed in the pin map CSV, measured from the index notch, positive toward +Y viewed from +Z. Angular tolerance +/-0.5 deg.",
    f"- Index notch {mm(C['index_notch_width'])} wide x {mm(C['index_notch_depth'])} deep at 0 deg on the Z=0 end: the tune start and the angular datum.",
    f"- Press fit for {mm(PIN['diameter'])} hardened music wire pins. Holes are {mm(PIN['diameter'] - C['hole_diameter'])} under pin size.",
    "", "## Punch callouts", "",
    f"- Bore {mm(PIN['diameter'] + PU['bore_clearance'])} +0.01/-0, depth {mm(PIN['standoff'])} +/-0.02 from the lowest point of the concave face. This depth sets pin height.",
    f"- Concave face radius {mm(R)} to match the cylinder. Tip {mm(PU['tip_diameter'])} diameter, body {mm(PU['body_diameter'])} to suit a drill chuck.",
    "- Harden if convenient; not required for one cylinder.",
    "", "## Jig callouts", "",
    f"- Plate thickness {mm(PIN['length'])} +/-0.02, faces ground parallel. This is the pin length.",
    f"- {J['hole_count']} holes {mm(PIN['diameter'] + J['hole_clearance'])} +0.01/-0 reamed, on {mm(J['hole_pitch'])} pitch. Two {mm(J['dowel_diameter'])} dowel holes locate the plate on the base; dowel pins are stock.",
    "", "## Cradle", "",
    f"- Holds the cylinder by a {mm(C['bore_diameter'])} arbor (stock drill rod) in V notches; the pinned surface never touches anything. Fine in wood.",
    "", "## Not yet measured, placeholders in params.json", "",
    "- Cylinder diameter, length, bore, and how the original is driven.",
    "- Pin diameter, standoff and length from the original cylinder.",
    "- Tooth pitch and the first row offset from the comb.",
]
with open(os.path.join(OUT, "SUMMARY.md"), "w") as f:
    f.write("\n".join(lines) + "\n")
print("wrote", os.path.join(OUT, "SUMMARY.md"))
