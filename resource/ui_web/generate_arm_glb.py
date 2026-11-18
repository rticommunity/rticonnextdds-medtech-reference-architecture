#!/usr/bin/env python3
"""Reproducibly generate the original, lightweight articulated-arm GLB asset."""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "modules" / "01-operating-room" / "src"),
)

from ArmKinematics import (  # noqa: E402, I001
    BASE_HEIGHT_M as BASE_HEIGHT,
    FOREARM_M as FOREARM,
    INITIAL_JAW_GAP_M,
    MAX_JAW_GAP_M,
    TCP_OFFSET_M as TCP_OFFSET,
    UPPER_ARM_M as UPPER_ARM,
)

FINGER_LENGTH = 0.072
PAD_WIDTH = 0.012
PALM_DEPTH = 0.020
PALM_Z = -FINGER_LENGTH - 0.004
SHAFT_LENGTH = TCP_OFFSET + PALM_Z
OUTPUT = Path(__file__).resolve().parent / "models" / "articulated-arm.glb"


def _hex_color(value: str) -> list[float]:
    return [int(value[index : index + 2], 16) / 255.0 for index in (1, 3, 5)] + [1.0]


class GlbBuilder:
    def __init__(self) -> None:
        self.binary = bytearray()
        self.buffer_views = []
        self.accessors = []
        self.meshes = []
        self.nodes = []
        self.materials = []
        self.material_ids = {}

    def material(
        self, name: str, color: str, metallic: float = 0.25, roughness: float = 0.48
    ) -> int:
        material_id = len(self.materials)
        self.materials.append(
            {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": _hex_color(color),
                    "metallicFactor": metallic,
                    "roughnessFactor": roughness,
                },
            }
        )
        self.material_ids[name] = material_id
        return material_id

    def _append_data(self, data: bytes, target: int) -> int:
        while len(self.binary) % 4:
            self.binary.append(0)
        offset = len(self.binary)
        self.binary.extend(data)
        view_id = len(self.buffer_views)
        self.buffer_views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target}
        )
        return view_id

    def _accessor(
        self, view: int, component: int, count: int, kind: str, values, minmax=False
    ) -> int:
        accessor = {
            "bufferView": view,
            "byteOffset": 0,
            "componentType": component,
            "count": count,
            "type": kind,
        }
        if minmax:
            width = len(values[0]) if isinstance(values[0], tuple) else 1
            columns = list(zip(*values)) if width > 1 else [values]
            accessor["min"] = [min(column) for column in columns]
            accessor["max"] = [max(column) for column in columns]
        accessor_id = len(self.accessors)
        self.accessors.append(accessor)
        return accessor_id

    def mesh(self, name: str, vertices, normals, indices, material: str) -> int:
        position_bytes = b"".join(struct.pack("<3f", *vertex) for vertex in vertices)
        normal_bytes = b"".join(struct.pack("<3f", *normal) for normal in normals)
        index_bytes = b"".join(struct.pack("<H", index) for index in indices)
        position_view = self._append_data(position_bytes, 34962)
        normal_view = self._append_data(normal_bytes, 34962)
        index_view = self._append_data(index_bytes, 34963)
        position_accessor = self._accessor(
            position_view, 5126, len(vertices), "VEC3", vertices, minmax=True
        )
        normal_accessor = self._accessor(normal_view, 5126, len(normals), "VEC3", normals)
        index_accessor = self._accessor(index_view, 5123, len(indices), "SCALAR", indices)
        mesh_id = len(self.meshes)
        self.meshes.append(
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {"POSITION": position_accessor, "NORMAL": normal_accessor},
                        "indices": index_accessor,
                        "material": self.material_ids[material],
                        "mode": 4,
                    }
                ],
            }
        )
        return mesh_id

    def node(
        self, name: str, parent: int | None = None, *, mesh=None, translation=None, rotation=None
    ) -> int:
        node = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if translation is not None:
            node["translation"] = list(translation)
        if rotation is not None:
            node["rotation"] = list(rotation)
        index = len(self.nodes)
        self.nodes.append(node)
        if parent is not None:
            self.nodes[parent].setdefault("children", []).append(index)
        return index

    def write(self, root: int) -> None:
        document = {
            "asset": {"version": "2.0", "generator": "generate_arm_glb.py"},
            "scene": 0,
            "scenes": [{"nodes": [root]}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "buffers": [{"byteLength": len(self.binary)}],
            "bufferViews": self.buffer_views,
            "accessors": self.accessors,
        }
        json_chunk = json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
        binary_chunk = bytes(self.binary)
        binary_chunk += b"\0" * ((4 - len(binary_chunk) % 4) % 4)
        total_size = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
        glb = (
            struct.pack("<4sII", b"glTF", 2, total_size)
            + struct.pack("<I4s", len(json_chunk), b"JSON")
            + json_chunk
            + struct.pack("<I4s", len(binary_chunk), b"BIN\0")
            + binary_chunk
        )
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(glb)


def box(name: str, dimensions, material: str):
    dx, dy, dz = dimensions
    faces = [
        ((1, 0, 0), ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))),
        ((-1, 0, 0), ((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1))),
        ((0, 1, 0), ((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1))),
        ((0, -1, 0), ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1))),
        ((0, 0, 1), ((1, -1, 1), (1, 1, 1), (-1, 1, 1), (-1, -1, 1))),
        ((0, 0, -1), ((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1))),
    ]
    vertices, normals, indices = [], [], []
    for normal, corners in faces:
        base = len(vertices)
        vertices.extend((x * dx / 2, y * dy / 2, z * dz / 2) for x, y, z in corners)
        normals.extend([normal] * 4)
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    return name, vertices, normals, indices, material


def cylinder(
    name: str, length: float, radius: float, material: str, *, axis: str = "z", segments: int = 20
):
    vertices, normals, indices = [], [], []

    def point(along, angle):
        cosine, sine = math.cos(angle), math.sin(angle)
        if axis == "x":
            return (along, radius * cosine, radius * sine), (0.0, cosine, sine)
        return (radius * cosine, radius * sine, along), (cosine, sine, 0.0)

    for index in range(segments):
        angle0 = 2 * math.pi * index / segments
        angle1 = 2 * math.pi * (index + 1) / segments
        base = len(vertices)
        v00, n00 = point(-length / 2, angle0)
        v01, n01 = point(-length / 2, angle1)
        v11, n11 = point(length / 2, angle1)
        v10, n10 = point(length / 2, angle0)
        vertices.extend((v00, v01, v11, v10))
        normals.extend((n00, n01, n11, n10))
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    for along, direction in ((-length / 2, -1.0), (length / 2, 1.0)):
        center = len(vertices)
        end_normal = (direction, 0, 0) if axis == "x" else (0, 0, direction)
        vertices.append((along, 0, 0) if axis == "x" else (0, 0, along))
        normals.append(end_normal)
        for index in range(segments):
            point_value, _ = point(along, 2 * math.pi * index / segments)
            vertices.append(point_value)
            normals.append(end_normal)
        for index in range(segments):
            a, b = center + 1 + index, center + 1 + (index + 1) % segments
            indices.extend((center, b, a) if direction < 0 else (center, a, b))
    return name, vertices, normals, indices, material


def turned_housing(name: str, profile, material: str, *, axis="z", segments=40):
    """Create a smoothly shaded housing from axial positions and radii."""
    vertices, normals, indices = [], [], []

    def vector(along, radial, angle):
        x, y = radial * math.cos(angle), radial * math.sin(angle)
        if axis == "x":
            return (along, x, y)
        if axis == "y":
            return (x, along, -y)
        return (x, y, along)

    for row, (position, radius) in enumerate(profile):
        before = profile[max(0, row - 1)]
        after = profile[min(len(profile) - 1, row + 1)]
        slope = (after[1] - before[1]) / (after[0] - before[0])
        normal_scale = math.hypot(slope, 1)
        for column in range(segments):
            angle = 2 * math.pi * column / segments
            vertices.append(vector(position, radius, angle))
            normals.append(vector(-slope / normal_scale, 1 / normal_scale, angle))
    for row in range(len(profile) - 1):
        for column in range(segments):
            a = row * segments + column
            b = row * segments + (column + 1) % segments
            c, d = b + segments, a + segments
            indices.extend((a, b, c, a, c, d))
    for row, direction in ((0, -1), (len(profile) - 1, 1)):
        center = len(vertices)
        vertices.append(vector(profile[row][0], 0, 0))
        normals.append(vector(direction, 0, 0))
        for column in range(segments):
            angle = 2 * math.pi * column / segments
            vertices.append(vector(profile[row][0], profile[row][1], angle))
            normals.append(vector(direction, 0, angle))
        for column in range(segments):
            a, b = center + 1 + column, center + 1 + (column + 1) % segments
            indices.extend((center, b, a) if direction < 0 else (center, a, b))
    return name, vertices, normals, indices, material


def ring(name: str, radius: float, thickness: float, material: str, segments=48):
    vertices, normals, indices = [], [], []
    inner, outer = radius - thickness / 2, radius + thickness / 2
    for index in range(segments):
        angle0 = 2 * math.pi * index / segments
        angle1 = 2 * math.pi * (index + 1) / segments
        base = len(vertices)
        vertices.extend(
            (
                (inner * math.cos(angle0), inner * math.sin(angle0), 0),
                (outer * math.cos(angle0), outer * math.sin(angle0), 0),
                (outer * math.cos(angle1), outer * math.sin(angle1), 0),
                (inner * math.cos(angle1), inner * math.sin(angle1), 0),
            )
        )
        normals.extend([(0, 0, 1)] * 4)
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    return name, vertices, normals, indices, material


def main() -> None:
    glb = GlbBuilder()
    for name, color, metallic in (
        ("graphite", "#27333c", 0.4),
        ("steel", "#9aa9b3", 0.5),
        ("silver", "#e0e5e8", 0.25),
        ("blue", "#1476b3", 0.35),
        ("cyan", "#37adc0", 0.2),
        ("orange", "#ed8b00", 0.2),
        ("axis_x", "#ff5252", 0.0),
        ("axis_y", "#00e676", 0.0),
        ("axis_z", "#448aff", 0.0),
        ("floor", "#344557", 0.1),
    ):
        glb.material(name, color, metallic)

    geometries = [
        turned_housing(
            "base-block",
            [(-0.07, 0.08), (-0.065, 0.09), (0.045, 0.09), (0.065, 0.075), (0.07, 0.07)],
            "graphite",
        ),
        turned_housing(
            "yaw-bearing",
            [(-0.022, 0.064), (-0.016, 0.071), (0.012, 0.071), (0.022, 0.061)],
            "steel",
        ),
        turned_housing(
            "shoulder-housing",
            [
                (-0.045, 0.035),
                (-0.039, 0.05),
                (-0.03, 0.055),
                (0.03, 0.055),
                (0.039, 0.05),
                (0.045, 0.035),
            ],
            "silver",
            axis="y",
        ),
        turned_housing(
            "upper-arm",
            [
                (-UPPER_ARM / 2, 0.029),
                (-UPPER_ARM / 2 + 0.025, 0.04),
                (-0.05, 0.042),
                (0.055, 0.037),
                (UPPER_ARM / 2 - 0.025, 0.033),
                (UPPER_ARM / 2, 0.025),
            ],
            "silver",
            axis="x",
        ),
        turned_housing(
            "elbow-housing",
            [
                (-0.038, 0.029),
                (-0.033, 0.041),
                (-0.027, 0.046),
                (0.027, 0.046),
                (0.033, 0.041),
                (0.038, 0.029),
            ],
            "silver",
            axis="y",
        ),
        turned_housing(
            "forearm",
            [
                (-FOREARM / 2, 0.026),
                (-FOREARM / 2 + 0.025, 0.035),
                (-0.04, 0.036),
                (0.045, 0.032),
                (FOREARM / 2 - 0.02, 0.029),
                (FOREARM / 2, 0.023),
            ],
            "silver",
            axis="x",
        ),
        turned_housing(
            "wrist-housing",
            [
                (-0.037, 0.025),
                (-0.03, 0.035),
                (-0.02, 0.037),
                (0.02, 0.037),
                (0.03, 0.033),
                (0.037, 0.025),
            ],
            "steel",
        ),
        turned_housing(
            "wrist-ring",
            [(-0.006, 0.035), (-0.004, 0.039), (0.004, 0.039), (0.006, 0.035)],
            "graphite",
        ),
        turned_housing(
            "joint-cap",
            [(-0.003, 0.026), (-0.001, 0.032), (0.001, 0.032), (0.003, 0.026)],
            "graphite",
            axis="y",
        ),
        turned_housing(
            "joint-accent", [(-0.001, 0.017), (0, 0.020), (0.001, 0.017)], "blue", axis="y"
        ),
        turned_housing(
            "base-trim", [(-0.004, 0.087), (-0.002, 0.091), (0.002, 0.091), (0.004, 0.087)], "steel"
        ),
        cylinder("tool-shaft", SHAFT_LENGTH, 0.014, "silver"),
        box("gripper-palm", (MAX_JAW_GAP_M + 2 * PAD_WIDTH + 0.010, 0.036, PALM_DEPTH), "graphite"),
        box("tool-roll-mark", (0.028, 0.009, 0.018), "orange"),
        box("finger", (0.009, 0.014, FINGER_LENGTH), "silver"),
        box("finger-pad", (PAD_WIDTH, 0.019, 0.012), "cyan"),
        ring("workspace-ring", 0.33, 0.003, "floor"),
        box("axis-x", (0.12, 0.004, 0.004), "axis_x"),
        box("axis-y", (0.004, 0.12, 0.004), "axis_y"),
        box("axis-z", (0.004, 0.004, 0.12), "axis_z"),
    ]
    meshes = {
        name: glb.mesh(name, vertices, normals, indices, material)
        for name, vertices, normals, indices, material in geometries
    }

    # The arm's model frame is Z-up. This fixed root transform maps it to the
    # Y-up view used by the SDK without changing any backend pose coordinates.
    root = glb.node(
        "Arm",
        rotation=(-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)),
    )
    glb.node("Base", root, mesh=meshes["base-block"], translation=(0, 0, 0.07))
    base_yaw = glb.node(
        "BaseYaw", root, mesh=meshes["yaw-bearing"], translation=(0, 0, BASE_HEIGHT)
    )
    shoulder = glb.node("Shoulder", base_yaw, mesh=meshes["shoulder-housing"])
    for sign in (-1, 1):
        glb.node(
            f"ShoulderCap{sign}",
            shoulder,
            mesh=meshes["joint-cap"],
            translation=(0, sign * 0.046, 0),
        )
        glb.node(
            f"ShoulderAccent{sign}",
            shoulder,
            mesh=meshes["joint-accent"],
            translation=(0, sign * 0.050, 0),
        )
    glb.node("UpperLink", shoulder, mesh=meshes["upper-arm"], translation=(UPPER_ARM / 2, 0, 0))
    elbow = glb.node(
        "Elbow",
        shoulder,
        mesh=meshes["elbow-housing"],
        translation=(UPPER_ARM, 0, 0),
    )
    for sign in (-1, 1):
        glb.node(
            f"ElbowCap{sign}", elbow, mesh=meshes["joint-cap"], translation=(0, sign * 0.039, 0)
        )
        glb.node(
            f"ElbowAccent{sign}",
            elbow,
            mesh=meshes["joint-accent"],
            translation=(0, sign * 0.043, 0),
        )
    glb.node("ForearmLink", elbow, mesh=meshes["forearm"], translation=(FOREARM / 2, 0, 0))
    wrist = glb.node(
        "Wrist",
        elbow,
        mesh=meshes["wrist-housing"],
        translation=(FOREARM, 0, 0),
    )
    glb.node("WristRollCue", wrist, mesh=meshes["wrist-ring"], translation=(0, 0, -0.02))
    tool = glb.node("Tool", wrist, translation=(0, 0, TCP_OFFSET))
    glb.node(
        "ToolShaft",
        tool,
        mesh=meshes["tool-shaft"],
        translation=(0, 0, -TCP_OFFSET + SHAFT_LENGTH / 2),
    )
    glb.node("GripperPalm", tool, mesh=meshes["gripper-palm"], translation=(0, 0, PALM_Z))
    glb.node(
        "ToolRollMark",
        tool,
        mesh=meshes["tool-roll-mark"],
        translation=(0, 0.0225, PALM_Z),
    )
    # Animated finger origins are the opposing contact faces at the TCP plane.
    # Static children retain their geometry offsets when live poses are applied.
    for side, sign in (("Left", 1), ("Right", -1)):
        finger = glb.node(f"{side}Finger", tool, translation=(sign * INITIAL_JAW_GAP_M / 2, 0, 0))
        glb.node(
            f"{side}FingerBody",
            finger,
            mesh=meshes["finger"],
            translation=(sign * PAD_WIDTH / 2, 0, -FINGER_LENGTH / 2),
        )
        glb.node(
            f"{side}FingerPad",
            finger,
            mesh=meshes["finger-pad"],
            translation=(sign * PAD_WIDTH / 2, 0, 0),
        )
    workspace = glb.node("Workspace", root)
    glb.node("BaseTrim", root, mesh=meshes["base-trim"], translation=(0, 0, 0.025))
    glb.node("ReferenceRing", workspace, mesh=meshes["workspace-ring"], translation=(0, 0, 0.004))
    glb.node("AxisX", workspace, mesh=meshes["axis-x"], translation=(0.06, 0, 0.008))
    glb.node("AxisY", workspace, mesh=meshes["axis-y"], translation=(0, 0.06, 0.008))
    glb.node("AxisZ", workspace, mesh=meshes["axis-z"], translation=(0, 0, 0.06))
    glb.write(root)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
