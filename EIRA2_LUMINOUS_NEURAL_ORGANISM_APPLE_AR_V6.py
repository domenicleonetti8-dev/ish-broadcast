from __future__ import annotations

import math
import struct
import time
import zipfile
import zlib
from pathlib import Path
from typing import Any

SCHEMA = "eira2_luminous_neural_organism_apple_ar_v6"
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def _safe(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(value or ""))
    if not text or text[0].isdigit():
        text = "n_" + text
    return text[:96]


def _nid(row: dict[str, Any]) -> str:
    return str(row.get("_id") or row.get("id") or "")


def _all(atlas: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    page = atlas.page(cursor=0, limit=5000, include_paths=False)
    neurons = [dict(x) for x in (page.get("neurons") or []) if isinstance(x, dict)]
    fibers = [dict(x) for x in ((atlas.fibers_for(limit=30000) or {}).get("fibers") or []) if isinstance(x, dict)]
    seen = {_nid(x) for x in neurons if _nid(x)}
    for f in fibers:
        for key in ("source", "target"):
            ident = str(f.get(key) or "")
            if ident and ident not in seen:
                row = atlas.neuron(ident)
                if row:
                    neurons.append(dict(row))
                    seen.add(ident)
    return neurons, fibers


def _region(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(k) or "") for k in ("_id", "id", "logical_path", "kind", "cluster")).casefold()
    rules = (
        ("universe_library", "universe_library"), ("memory", "memory"), ("history", "memory"),
        ("evidence", "evidence"), ("reason", "reasoning"), ("identity", "identity"),
        ("delivery", "delivery"), ("conversation", "conversation_spine"), ("watcher", "watcher"),
        ("superprobe", "superprobe"), ("extension", "extensions"), ("learn", "learning"),
    )
    for needle, region in rules:
        if needle in text:
            return region
    return "organism"


def _positions(neurons: list[dict[str, Any]]) -> dict[str, tuple[float, float, float]]:
    left = [n for n in neurons if n.get("hemisphere") == "left" and not n.get("spine")]
    right = [n for n in neurons if n.get("hemisphere") == "right" and not n.get("spine")]
    mid = [n for n in neurons if n not in left and n not in right]
    out: dict[str, tuple[float, float, float]] = {}

    def side(items: list[dict[str, Any]], sign: float) -> None:
        total = max(1, len(items))
        for i, row in enumerate(sorted(items, key=_nid)):
            u = (i + 0.5) / total
            z = 1.0 - 2.0 * u
            rr = math.sqrt(max(0.0, 1.0 - z * z))
            theta = i * GOLDEN + (0.0 if sign < 0 else math.pi / 7.0)
            x = sign * (0.04 + 0.90 * abs(rr * math.cos(theta)))
            y = 0.94 * rr * math.sin(theta)
            zz = 0.94 * z
            length = math.sqrt(x*x + y*y + zz*zz) or 1.0
            shell = 0.88 + 0.06 * ((i % 13) / 12.0)
            out[_nid(row)] = (x/length*shell, y/length*shell, zz/length*shell)

    side(left, -1.0)
    side(right, 1.0)
    spine = [r for r in mid if r.get("spine")]
    other = [r for r in mid if not r.get("spine")]
    for i, row in enumerate(sorted(spine, key=_nid)):
        t = 0.5 if len(spine) == 1 else i / max(1, len(spine) - 1)
        out[_nid(row)] = (0.0, 0.0, -0.94 + 1.88 * t)
    for i, row in enumerate(sorted(other, key=_nid)):
        a = i * GOLDEN
        r = 0.18 + 0.10 * ((i % 9) / 8.0)
        out[_nid(row)] = (r * math.cos(a), r * math.sin(a), -0.22 + 0.44 * ((i % 17) / 16.0))
    return out


def _material(lines: list[str], name: str, rgb: tuple[float,float,float], emit: tuple[float,float,float], opacity: float = 1.0) -> None:
    lines += [
        f'        def Material "{name}" {{',
        f'            token outputs:surface.connect = </Brain/Looks/{name}/Shader.outputs:surface>',
        '            def Shader "Shader" {',
        '                uniform token info:id = "UsdPreviewSurface"',
        f'                color3f inputs:diffuseColor = ({rgb[0]:.6f}, {rgb[1]:.6f}, {rgb[2]:.6f})',
        f'                color3f inputs:emissiveColor = ({emit[0]:.6f}, {emit[1]:.6f}, {emit[2]:.6f})',
        f'                float inputs:opacity = {opacity:.6f}',
        '                float inputs:metallic = 0.05',
        '                float inputs:roughness = 0.14',
        '                token outputs:surface',
        '            }',
        '        }',
    ]


def _cylinder(a: tuple[float,float,float], b: tuple[float,float,float]) -> tuple[tuple[float,float,float], tuple[float,float,float], float]:
    dx, dy, dz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    mid = ((a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2)
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(math.sqrt(dx*dx + dy*dy), dz))
    return mid, (0.0, pitch, yaw), length


def _tube(lines: list[str], name: str, a: tuple[float,float,float], b: tuple[float,float,float], radius: float, material: str) -> None:
    mid, rot, length = _cylinder(a, b)
    if length <= 1e-7:
        return
    lines += [
        f'    def Xform "{_safe(name)}" {{',
        f'        double3 xformOp:translate = ({mid[0]:.6f}, {mid[1]:.6f}, {mid[2]:.6f})',
        f'        float3 xformOp:rotateXYZ = ({rot[0]:.6f}, {rot[1]:.6f}, {rot[2]:.6f})',
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]',
        '        def Cylinder "Axon" {',
        '            uniform token axis = "Z"',
        f'            double radius = {radius:.6f}',
        f'            double height = {length:.6f}',
        f'            rel material:binding = </Brain/Looks/{material}>',
        '        }',
        '    }',
    ]


def write_brain_usda(atlas: Any, path: Path) -> Path:
    neurons, fibers = _all(atlas)
    if not neurons:
        raise ValueError("apple_ar_no_canonical_neurons")
    positions = _positions(neurons)
    palette = ("Azure", "Cyan", "Violet", "Magenta", "Rose", "Amber", "Gold", "White")
    lines = ["#usda 1.0", "(", '    defaultPrim = "Brain"', "    metersPerUnit = 1", '    upAxis = "Z"', ")", "", 'def Xform "Brain" {', '    def Scope "Looks" {']
    looks = {
        "Azure": ((0.015,0.34,1.00),(0.05,0.58,1.00)), "Cyan": ((0.005,0.82,1.00),(0.04,1.00,1.00)),
        "Violet": ((0.35,0.02,1.00),(0.68,0.08,1.00)), "Magenta": ((1.00,0.02,0.64),(1.00,0.08,0.82)),
        "Rose": ((1.00,0.04,0.26),(1.00,0.12,0.34)), "Amber": ((1.00,0.24,0.005),(1.00,0.62,0.02)),
        "Gold": ((1.00,0.48,0.01),(1.00,0.88,0.04)), "White": ((0.88,0.98,1.00),(1.00,1.00,1.00)),
        "Shell": ((0.01,0.08,0.22),(0.01,0.12,0.30)),
    }
    for name, (rgb, emit) in looks.items():
        _material(lines, name, rgb, emit, 0.035 if name == "Shell" else 1.0)
    lines += ["    }"]
    lines += ['    def Sphere "OrganismEnvelope" {', '        double radius = 1.0', '        rel material:binding = </Brain/Looks/Shell>', '    }']
    for i, (radius, material) in enumerate(((0.185,"Amber"),(0.135,"Gold"),(0.092,"White"),(0.050,"Amber"))):
        lines += [f'    def Sphere "CoreGlow_{i}" {{', f'        double radius = {radius:.6f}', f'        rel material:binding = </Brain/Looks/{material}>', '    }']

    neuron_rows = []
    for i, row in enumerate(neurons):
        ident = _nid(row)
        pos = positions.get(ident)
        if not ident or pos is None:
            continue
        region = _region(row)
        if row.get("spine"):
            material = "White"
            radius = 0.016
        else:
            material = palette[i % len(palette)]
            radius = 0.010 if i % 13 else 0.019
        neuron_rows.append((ident, pos, material, row))
        lines += [
            f'    def Xform "Neuron_{i:04d}_{_safe(ident)}" {{',
            f'        double3 xformOp:translate = ({pos[0]:.6f}, {pos[1]:.6f}, {pos[2]:.6f})',
            '        uniform token[] xformOpOrder = ["xformOp:translate"]',
            '        def Sphere "Soma" {',
            f'            double radius = {radius:.6f}',
            f'            rel material:binding = </Brain/Looks/{material}>',
            f'            custom string eira:nodeId = "{_safe(ident)}"',
            f'            custom string eira:region = "{region}"',
            '            custom string eira:reactivity = "runtime_activity_driven"',
            '        }',
            '    }',
        ]

    fiber_count = 0
    for i, f in enumerate(fibers):
        a = positions.get(str(f.get("source") or ""))
        b = positions.get(str(f.get("target") or ""))
        if not a or not b or a == b:
            continue
        mid = tuple((a[k]+b[k])/2 for k in range(3))
        ml = math.sqrt(sum(v*v for v in mid)) or 1.0
        bend = 0.012 if i % 2 == 0 else -0.012
        control = tuple(mid[k] + mid[k]/ml*bend for k in range(3))
        material = "Cyan" if f.get("conductive") else "Violet"
        _tube(lines, f"Fiber_{i:05d}_A", a, control, 0.0017 if f.get("conductive") else 0.0010, material)
        _tube(lines, f"Fiber_{i:05d}_B", control, b, 0.0012 if f.get("conductive") else 0.0008, material)
        fiber_count += 1

    core_targets = neuron_rows[::max(1, len(neuron_rows)//40 or 1)][:40]
    for i, (_, pos, _, _) in enumerate(core_targets):
        q = tuple(v*0.62 for v in pos)
        c = tuple(v*0.28 for v in pos)
        material = "Gold" if i % 3 == 0 else "Amber"
        _tube(lines, f"CoreRoot_{i:03d}_A", (0.0,0.0,0.0), c, 0.0055, material)
        _tube(lines, f"CoreRoot_{i:03d}_B", c, q, 0.0035, material)
        _tube(lines, f"CoreRoot_{i:03d}_C", q, pos, 0.0018, material)

    for strand, phase, material in ((0,0.0,"Violet"),(1,math.pi,"Gold")):
        pts = []
        for i in range(180):
            t = i / 179
            a = phase + t * math.pi * 10.5
            pts.append((0.050*math.cos(a), 0.050*math.sin(a), -0.95+1.90*t))
        for i in range(len(pts)-1):
            _tube(lines, f"SpinalHelix_{strand}_{i:03d}", pts[i], pts[i+1], 0.0024, material)

    # Living Hall of Records is internal anatomy, not a second app/server.
    for floor in range(5):
        z = -0.13 + floor * 0.065
        r = 0.20 + floor * 0.028
        ring = []
        for k in range(36):
            a = 2*math.pi*k/36
            ring.append((r*math.cos(a), r*math.sin(a), z))
        for k in range(36):
            _tube(lines, f"ArchiveRing_{floor}_{k:02d}", ring[k], ring[(k+1)%36], 0.0019, "Gold" if floor%2==0 else "Cyan")
        for k in range(30):
            a = 2*math.pi*k/30 + floor*0.11
            p = (r*math.cos(a), r*math.sin(a), z)
            lines += [
                f'    def Xform "HallBook_{floor}_{k:02d}" {{',
                f'        double3 xformOp:translate = ({p[0]:.6f}, {p[1]:.6f}, {p[2]:.6f})',
                '        double3 xformOp:scale = (0.0065, 0.0110, 0.0038)',
                '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]',
                '        def Cube "Book" {',
                '            double size = 1',
                f'            rel material:binding = </Brain/Looks/{"Gold" if k%6==0 else "Azure"}>',
                f'            custom string eira:nodeId = "universe.library.floor{floor}.book{k:02d}"',
                '            custom string eira:interaction = "open_library_object"',
                '        }',
                '    }',
            ]

    lines += ["}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not fiber_count:
        raise ValueError("apple_ar_no_evidenced_fibers")
    return path


def package_usdz(root_layer: Path, output: Path) -> Path:
    data = root_layer.read_bytes()
    name = root_layer.name.encode("utf-8")
    crc = zlib.crc32(data) & 0xFFFFFFFF
    now = time.localtime()
    dostime = ((now.tm_hour & 31) << 11) | ((now.tm_min & 63) << 5) | ((now.tm_sec // 2) & 31)
    dosdate = (((now.tm_year - 1980) & 127) << 9) | ((now.tm_mon & 15) << 5) | (now.tm_mday & 31)
    base = 30 + len(name)
    pad = (-base) % 64
    if 0 < pad < 4:
        pad += 64
    extra = b""
    if pad:
        payload_len = pad - 4
        extra = struct.pack("<HH", 0xFFFF, payload_len) + b"\0" * payload_len
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, dostime, dosdate, crc, len(data), len(data), len(name), len(extra)) + name + extra
    central = struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, dostime, dosdate, crc, len(data), len(data), len(name), len(extra), 0, 0, 0, 0, 0) + name + extra
    cd_offset = len(local) + len(data)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central), cd_offset, 0)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(local + data + central + end)
    with zipfile.ZipFile(output, "r") as zf:
        if zf.testzip() is not None:
            raise ValueError("apple_ar_usdz_zip_integrity_failed")
        infos = zf.infolist()
        if len(infos) != 1 or infos[0].compress_type != zipfile.ZIP_STORED:
            raise ValueError("apple_ar_usdz_storage_contract_failed")
        info = infos[0]
        name_len = len(info.filename.encode("utf-8"))
        extra_len = len(info.extra)
        if (info.header_offset + 30 + name_len + extra_len) % 64 != 0:
            raise ValueError("apple_ar_usdz_alignment_failed")
    return output


def build_brain_usdz(atlas: Any, output: Path) -> Path:
    usda = output.with_suffix(".usda")
    write_brain_usda(atlas, usda)
    return package_usdz(usda, output)
