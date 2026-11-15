#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""Generate stubs/gi-stubs/repository/GtkGhostty.pyi from the built GIR.

    python3 tools/gen_stubs.py _build/src/GtkGhostty-1.gir [output]

The stubs follow PyGObject's calling conventions: array length arguments
are dropped, out arguments become part of the returned tuple, nullable
values are Optional, and each signal gets a typed connect() overload.
tests/test_stubs.py fails when the committed file is out of date.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    "c": "http://www.gtk.org/introspection/core/1.0",
    "glib": "http://www.gtk.org/introspection/glib/1.0",
}
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "stubs" / "gi-stubs" / "repository" / "GtkGhostty.pyi"

SCALARS = {
    "utf8": "str", "filename": "str", "gboolean": "bool",
    "gint": "int", "guint": "int", "gsize": "int", "gssize": "int", "gint64": "int",
    "guint64": "int", "guint8": "int", "gunichar": "str",
    "gdouble": "float", "gfloat": "float", "none": "None",
}
#: String properties that are NULL until set. g-ir-scanner cannot record
#: nullability for properties, so it is listed here.
NULLABLE_PROPERTIES = {"title", "current-directory-uri"}
KEYWORDS = {"def", "class", "from", "in", "is", "lambda", "global", "pass", "return"}


def py_type(node, local: str, *, element=False) -> str:
    array = node.find("c:array", NS)
    if array is not None:
        inner = array.find("c:type", NS)
        name = inner.get("name") if inner is not None else "gpointer"
        if name == "guint8":
            return "bytes"
        return f"typing.Sequence[{py_type(array, local, element=True)}]"
    tnode = node.find("c:type", NS)
    name = tnode.get("name") if tnode is not None else "none"
    if name in SCALARS:
        return SCALARS[name]
    if "." in name:
        return name
    return name if element else name  # a type of this namespace


def nullable(node) -> bool:
    return node.get("nullable") == "1" or node.get("allow-none") == "1"


def opt(text: str, is_nullable: bool) -> str:
    return f"typing.Optional[{text}]" if is_nullable and text != "None" else text


def ident(name: str) -> str:
    name = name.replace("-", "_")
    return name + "_" if name in KEYWORDS else name


def callable_parts(fn, local: str):
    """(in-parameters, return annotation) as PyGObject presents them."""
    params = fn.find("c:parameters", NS)
    skip = set()
    plist = [p for p in (params if params is not None else []) if p.tag == f"{{{NS['c']}}}parameter"]
    for p in plist:
        array = p.find("c:array", NS)
        if array is not None and array.get("length") is not None:
            skip.add(int(array.get("length")))
    ins, outs = [], []
    ret = fn.find("c:return-value", NS)
    rtype = opt(py_type(ret, local), nullable(ret))
    if ret.find("c:array", NS) is not None and ret.find("c:array", NS).get("length") is not None:
        skip.add(int(ret.find("c:array", NS).get("length")))
    if rtype != "None":
        outs.append(rtype)
    for index, p in enumerate(plist):
        if index in skip:
            continue
        # An optional out argument only means C may pass NULL; Python always
        # gets the value back.
        is_out = p.get("direction") in ("out", "inout")
        annotation = opt(py_type(p, local), p.get("nullable") == "1" if is_out else nullable(p))
        if is_out:
            outs.append(annotation)
            if p.get("direction") == "out":
                continue
        ins.append(f"{ident(p.get('name'))}: {annotation}")
    if not outs:
        result = "None"
    elif len(outs) == 1:
        result = outs[0]
    else:
        result = f"typing.Tuple[{', '.join(outs)}]"
    return ins, result


def doc_of(node) -> str:
    """The first paragraph of the doc comment, gtk-doc markup made Python."""
    doc = node.find("c:doc", NS)
    if doc is None or not (doc.text or "").strip():
        return ""
    text = doc.text.strip().split("\n\n")[0].replace("\n", " ")
    text = re.sub(r"%NULL\b", "None", text)
    text = re.sub(r"%TRUE\b", "True", text)
    text = re.sub(r"%FALSE\b", "False", text)
    text = re.sub(r"#GtkGhostty(\w+)::([\w-]+)", r"the \1 '\2' signal", text)
    text = re.sub(r"#GtkGhostty(\w+):([\w-]+)", r"the \1 '\2' property", text)
    text = re.sub(r"gtk_ghostty_(terminal|pty)_(\w+)\(\)", r"\2()", text)
    text = re.sub(r"@(\w+)", r"\1", text)
    return text.replace('"""', "'''").replace("\\", "\\\\")


def emit_method(lines, fn, local, *, kind):
    ins, result = callable_parts(fn, local)
    name = ident(fn.get("name"))
    doc = doc_of(fn)
    if kind == "constructor":
        lines.append("    @classmethod")
        args = ", ".join(["cls"] + ins)
    elif kind == "function":
        lines.append("    @staticmethod")
        args = ", ".join(ins)
    else:
        args = ", ".join(["self"] + ins)
    if fn.get("throws") == "1":
        doc = (doc + " " if doc else "") + "Raises GLib.Error on failure."
    body = f'"""{doc}"""' if doc else "..."
    lines.append(f"    def {name}({args}) -> {result}: {body}")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    gir = ET.parse(argv[0]).getroot()
    output = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    namespace = gir.find("c:namespace", NS)
    local = namespace.get("name")
    lines = [
        "# SPDX-License-Identifier: LGPL-2.1-or-later",
        "# Generated by tools/gen_stubs.py from GtkGhostty-1.gir; do not edit.",
        "import typing",
        "",
        "from gi.repository import GLib, GObject, Gdk, Gtk, Pango",
        "",
    ]
    for enum in namespace.findall("c:enumeration", NS):
        lines.append(f"class {enum.get('name')}(GObject.GEnum):")
        for member in enum.findall("c:member", NS):
            lines.append(f"    {member.get('name').upper()}: {enum.get('name')}")
        lines.append("")
    for cls in namespace.findall("c:class", NS):
        name = cls.get("name")
        bases = [cls.get("parent")] + [i.get("name") for i in cls.findall("c:implements", NS)]
        lines.append(f"class {name}({', '.join(bases)}):")
        doc = doc_of(cls)
        if doc:
            lines.append(f'    """{doc}"""')
        props = cls.findall("c:property", NS)
        if props:
            lines.append(f"    class Props({cls.get('parent')}.Props):")
            for prop in props:
                lines.append(f"        {ident(prop.get('name'))}: "
                             f"{opt(py_type(prop, local), prop.get('name') in NULLABLE_PROPERTIES)}")
            lines.append("    props: Props")
        lines.append("    def __init__(self, **properties: typing.Any) -> None: ...")
        for fn in cls.findall("c:constructor", NS):
            emit_method(lines, fn, local, kind="constructor")
        for fn in cls.findall("c:function", NS):
            emit_method(lines, fn, local, kind="function")
        for fn in cls.findall("c:method", NS):
            emit_method(lines, fn, local, kind="method")
        signals = cls.findall("glib:signal", NS)
        for signal in signals:
            params = signal.find("c:parameters", NS)
            types = [opt(py_type(p, local), nullable(p)) for p in (params if params is not None else [])]
            handler = f"typing.Callable[[{', '.join([name] + types)}], typing.Any]"
            lines.append("    @typing.overload")
            lines.append(f"    def connect(self, detailed_signal: typing.Literal[\"{signal.get('name')}\"], "
                         f"handler: {handler}, *args: typing.Any) -> int: ...")
        if signals:
            lines.append("    @typing.overload")
            lines.append("    def connect(self, detailed_signal: str, handler: typing.Callable[..., typing.Any], "
                         "*args: typing.Any) -> int: ...")
        lines.append("")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
