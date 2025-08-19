# src/core/diff_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Iterable, Tuple
import difflib
import re


@dataclass
class DiffRow:
    tag: str                    # 'equal' | 'replace' | 'delete' | 'insert'
    left_no: int | None
    right_no: int | None
    left_text: str | None
    right_text: str | None
    left_html: str | None = None
    right_html: str | None = None


def _normalize_lines(
    lines: List[str],
    ignore_ws: bool,
    ignore_case: bool,
    normalize_eol: bool
) -> List[str]:
    out: List[str] = []
    for s in lines:
        x = s
        if normalize_eol:
            x = x.replace("\r\n", "\n").replace("\r", "\n")
        if ignore_ws:
            x = re.sub(r"\s+", " ", x).strip()
        if ignore_case:
            x = x.lower()
        out.append(x)
    return out


def _inline_diff_html(a: str, b: str) -> Tuple[str, str]:
    """Return (a_html, b_html) with inline highlights for replacements."""
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    a_parts: List[str] = []
    b_parts: List[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        a_seg = a[i1:i2]
        b_seg = b[j1:j2]
        if op == "equal":
            a_parts.append(_html_escape(a_seg))
            b_parts.append(_html_escape(b_seg))
        elif op == "insert":
            b_parts.append(f'<span style="background:#1f4;opacity:.25;">{_html_escape(b_seg)}</span>')
        elif op == "delete":
            a_parts.append(f'<span style="background:#f31;opacity:.25;">{_html_escape(a_seg)}</span>')
        else:  # replace
            a_parts.append(f'<span style="background:#f8b400;opacity:.35;">{_html_escape(a_seg)}</span>')
            b_parts.append(f'<span style="background:#f8b400;opacity:.35;">{_html_escape(b_seg)}</span>')
    return "".join(a_parts), "".join(b_parts)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace("\t", "    ")
         .replace(" ", "&nbsp;")
    )


def compute_diff(
    left_text: str,
    right_text: str,
    *,
    ignore_ws: bool = True,
    ignore_case: bool = False,
    normalize_eol: bool = True,
    inline: bool = True
) -> List[DiffRow]:
    """Produce side-by-side rows for table rendering."""
    # split as lines retaining endlines for nicer HTML spacing
    l_lines = left_text.splitlines(keepends=False)
    r_lines = right_text.splitlines(keepends=False)

    nl_l = _normalize_lines(l_lines, ignore_ws, ignore_case, normalize_eol)
    nl_r = _normalize_lines(r_lines, ignore_ws, ignore_case, normalize_eol)

    sm = difflib.SequenceMatcher(a=nl_l, b=nl_r, autojunk=False)

    rows: List[DiffRow] = []
    li = ri = 0  # 1-based line numbers for display
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        # slices in original (un-normalized) text for display
        l_chunk = l_lines[i1:i2]
        r_chunk = r_lines[j1:j2]

        if tag == "equal":
            for k in range(max(len(l_chunk), len(r_chunk))):
                ltxt = l_chunk[k] if k < len(l_chunk) else None
                rtxt = r_chunk[k] if k < len(r_chunk) else None
                li = li + 1 if ltxt is not None else li
                ri = ri + 1 if rtxt is not None else ri
                rows.append(DiffRow("equal",
                                    li if ltxt is not None else None,
                                    ri if rtxt is not None else None,
                                    ltxt, rtxt,
                                    _html_escape(ltxt) if ltxt is not None else None,
                                    _html_escape(rtxt) if rtxt is not None else None))
        elif tag == "delete":
            for ltxt in l_chunk:
                li += 1
                rows.append(DiffRow("delete", li, None, ltxt, None,
                                    _html_escape(ltxt), None))
        elif tag == "insert":
            for rtxt in r_chunk:
                ri += 1
                rows.append(DiffRow("insert", None, ri, None, rtxt,
                                    None, _html_escape(rtxt)))
        else:  # replace
            # align lengths for side-by-side
            m = max(len(l_chunk), len(r_chunk))
            for k in range(m):
                ltxt = l_chunk[k] if k < len(l_chunk) else None
                rtxt = r_chunk[k] if k < len(r_chunk) else None
                if ltxt is not None:
                    li += 1
                if rtxt is not None:
                    ri += 1

                if inline and (ltxt is not None and rtxt is not None):
                    lhtml, rhtml = _inline_diff_html(ltxt, rtxt)
                else:
                    lhtml = _html_escape(ltxt) if ltxt is not None else None
                    rhtml = _html_escape(rtxt) if rtxt is not None else None

                rows.append(DiffRow("replace",
                                    li if ltxt is not None else None,
                                    ri if rtxt is not None else None,
                                    ltxt, rtxt, lhtml, rhtml))
    return rows


def unified_patch(left_text: str, right_text: str, left_name: str = "left", right_name: str = "right") -> str:
    """Return unified diff text."""
    l = left_text.splitlines(keepends=True)
    r = right_text.splitlines(keepends=True)
    diff = difflib.unified_diff(l, r, fromfile=left_name, tofile=right_name, n=3)
    return "".join(diff)
