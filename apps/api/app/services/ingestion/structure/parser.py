"""Rule-based hierarchy parser for cleaned Indonesian legal documents."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from app.services.ingestion.domain import LegalSection, Page

_BAB_RE = re.compile(r"^BAB\s*([IVXLCDM]+)(?:\s+(.+))?$", re.IGNORECASE)
_BAGIAN_RE = re.compile(
    r"^Bagian\s+(Kesatu|Ke(?:dua|tiga|empat|lima|enam|tujuh|delapan|"
    r"sembilan|sepuluh|sebelas|dua belas)|[0-9]+)(?:\s+(.+))?$",
    re.IGNORECASE,
)
_PARAGRAF_RE = re.compile(r"^Paragraf\s+([0-9]+[A-Z]?)(?:\s+(.+))?$", re.IGNORECASE)
_PASAL_RE = re.compile(
    r"^[|\s]*Pasa[lI1]\s*([0-9O]+(?:\s+[0-9O]+)*[A-Z]?|I{1,3})(?:\s*[.,:]?\s*(.*))?$",
    re.IGNORECASE,
)
# An Ayat marker is a complete line marker or is followed by provision text.
# Do not treat a line such as ``(1), diperoleh ...`` as a new Ayat: PyMuPDF
# frequently wraps a cross-reference at exactly that boundary.
_AYAT_RE = re.compile(
    r"^\(\s*([0-9]+[A-Z]?)\s*\)(?:\s+(.+))?$",
    re.IGNORECASE,
)
_DOCUMENT_SECTION_RE = re.compile(
    r"^(Menimbang|Mengingat|MEMUTUSKAN|Menetapkan)\s*:?[ \t]*(.*)$",
    re.IGNORECASE,
)
_EXPLANATION_RE = re.compile(
    r"^P\s*E\s*N\s*J\s*E\s*[LI1][.]?\s*A\s*S\s*A\s*N(?:\s+ATAS\b.*)?$", re.IGNORECASE
)
_ATTACHMENT_RE = re.compile(r"^LAMPIRAN\b.*$", re.IGNORECASE)
_MALFORMED_MARKER_RE = re.compile(
    r"^(?:BAB|Bagian|Paragraf|Pasa[lI1])\s+[?\ufffd]+$",
    re.IGNORECASE,
)
_TRUNCATED_PASAL_HEADER_RE = re.compile(
    r"^(?:Pasa[lI1]\s*[0-9]+[A-Z]?|\(\d+\).*?)\s*(?:(?:\.\s*){2,}|…)$",
    re.IGNORECASE,
)
_PASAL_REFERENCE_TAIL_RE = re.compile(
    r"^(?:ayat\b|huruf\b|sampai\s+dengan\b|dan\s+Pasal\b|"
    r"sebagaimana\b|yang\s+dimaksud\b|dalam\b)",
    re.IGNORECASE,
)
_AMENDMENT_ITEM_RE = re.compile(
    r"^(?:Angka\s*)?\d+[.)]?\s+(?:Ketentuan\s+)?Pasa[lI1]\s*"
    r"[0-9]+(?:\s+[0-9]+)*[A-Z]?.*\b(?:diubah|dihapus|tetap)\b",
    re.IGNORECASE,
)
_AMENDMENT_BOUNDARY_RE = re.compile(
    r"^(?:Angka\s*)?\d+[.)]?\s+.*\b(?:diubah|dihapus|disisipkan|tetap)\b",
    re.IGNORECASE,
)
_AMENDMENT_OWNER_RE = re.compile(
    r"(?:\bbeberapa\s+ketentuan\s+dalam\b|\bketentuan\s+pasal\s+"
    r"[0-9O]+(?:\s+[0-9O]+)*[A-Z]?.*\b(?:diubah|dihapus|disisipkan|tetap)\b)",
    re.IGNORECASE,
)

_NAMED_ROLES = {
    "ketentuan umum": "ketentuan_umum",
    "ketentuan peralihan": "ketentuan_peralihan",
    "ketentuan penutup": "ketentuan_penutup",
}
_TITLE_CONNECTORS = {
    "atas",
    "atau",
    "bagi",
    "dan",
    "dari",
    "dengan",
    "serta",
    "tentang",
    "yang",
}


@dataclass
class _Node:
    type: str
    identifier: str
    node_id: str
    order: int
    parent: _Node | None
    title: str | None = None
    role: str | None = None
    parts: list[tuple[int, str]] = field(default_factory=list)
    children: list[_Node] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    amendment_scope: str | None = None


class IndonesianLegalStructureParser:
    """Parse cleaned pages with regexes and an explicit hierarchy state machine."""

    def parse(
        self,
        document_id: str,
        pages: Sequence[Page],
        *,
        document_title: str | None = None,
    ) -> list[LegalSection]:
        if not pages:
            return []

        self._document_id = document_id
        self._nodes: list[_Node] = []
        self._next_order = 0
        self._unstructured_count = 0
        first_page = min(page.page_number for page in pages)
        last_page = max(page.page_number for page in pages)
        self._root = self._new_node(
            "document",
            document_id,
            None,
            first_page,
            title=document_title,
        )
        self._root.page_end = last_page
        self._scope = self._root
        self._chapter: _Node | None = None
        self._bagian: _Node | None = None
        self._paragraf: _Node | None = None
        self._pasal: _Node | None = None
        self._ayat: _Node | None = None
        self._active: _Node = self._root
        self._pending_title: _Node | None = None
        self._memutuskan: _Node | None = None
        self._in_body = False
        self._amendment_scope: str | None = None
        self._pending_amendment_target = False
        self._lookahead = ""

        lines = [
            (page.page_number, line.strip())
            for page in sorted(pages, key=lambda item: item.page_number)
            for line in page.cleaned_text.splitlines()
            if line.strip()
        ]
        for index, (page_number, line) in enumerate(lines):
            lookahead = []
            for _, value in lines[index + 1 : index + 12]:
                if _PASAL_RE.fullmatch(value):
                    break
                lookahead.append(value)
            self._lookahead = " ".join(lookahead)
            marker = _PASAL_RE.fullmatch(line)
            following = lines[index + 1 : index + 10]
            # A catchword repeats the next page's heading at the bottom of
            # this page. Require that explicit adjacent-page evidence; never
            # collapse duplicate provisions on the same page.
            if marker and not _optional_text(marker.group(2)):
                same_page = sum(number == page_number for number, _ in following)
                repeats_next_page = any(
                    number == page_number + 1
                    and (other := _PASAL_RE.fullmatch(value))
                    and not _optional_text(other.group(2))
                    and other.group(1).casefold() == marker.group(1).casefold()
                    for number, value in following
                )
                if same_page <= 2 and repeats_next_page:
                    continue
            self._consume(line, page_number)

        sections = [self._freeze(node) for node in self._nodes]
        return _mark_source_duplicates(_derive_implicit_amendment_scopes(sections))

    def _consume(self, line: str, page_number: int) -> None:
        # Running headers such as ``Pasal 12 ...`` must not reset hierarchy or
        # create a second Pasal node when the actual provision follows.
        if _TRUNCATED_PASAL_HEADER_RE.match(line):
            return
        if self._amendment_scope and _AMENDMENT_ITEM_RE.match(line):
            # The next standalone Pasal is the quoted provision governed by
            # the active enacting article. Keep this signal independent of
            # the current visual hierarchy: omnibus PDFs frequently put the
            # target in a different Bagian or Paragraf.
            self._pending_amendment_target = True
        if (match := _DOCUMENT_SECTION_RE.match(line)) and not self._in_body:
            self._start_document_section(match.group(1), line, page_number)
            return
        if _EXPLANATION_RE.match(line):
            self._start_scope("penjelasan", "Penjelasan", line, page_number)
            return
        if _ATTACHMENT_RE.match(line):
            # Wrapped citations such as 'Lampiran / yang merupakan bagian'
            # are content, not the start of an annex.
            continuation = line[len("lampiran") :].strip() or self._lookahead
            if re.match(r"(?:yang|sebagaimana|ini|merupakan)\b", continuation, re.I):
                self._append(self._active, line, page_number)
            else:
                self._start_scope("lampiran", "Lampiran", line, page_number)
            return
        if match := _BAB_RE.match(line):
            self._start_bab(match, line, page_number)
            return
        if match := _BAGIAN_RE.match(line):
            self._start_bagian(match, line, page_number)
            return
        if match := _PARAGRAF_RE.match(line):
            self._start_paragraf(match, line, page_number)
            return
        if match := _PASAL_RE.match(line):
            tail = _optional_text(match.group(2))
            previous = self._active.parts[-1][1] if self._active.parts else ""
            continued_reference = self._pasal is not None and re.search(
                r"(?:\bdimaksud\s+(?:dalam|pada)|\bPasal\b.*\b(?:dan|atau)|\bdalam)\s*$",
                previous,
                re.I,
            )
            if not tail and not continued_reference:
                self._start_pasal(match, line, page_number)
                return
            # It is a cross-reference (for example ``Pasal 6 ayat (1)``),
            # not a malformed heading. Retain it under the current Ayat/Pasal
            # rather than clearing the hierarchy state below.
            self._append(self._active, line, page_number)
            return
        if match := _AYAT_RE.match(line):
            if self._active.parts and re.search(r"\bayat\s*$", self._active.parts[-1][1], re.I):
                self._append(self._active, line, page_number)
                return
            if self._pasal is None and self._scope.type == "lampiran":
                # Annex list numbers are not statutory Ayat.
                node = self._new_node("list_item", match.group(1), self._scope, page_number)
                self._active = node
                self._append(node, line, page_number)
                return
            self._start_ayat(match, line, page_number)
            return

        role = _NAMED_ROLES.get(_canonical_label(line))
        if role and self._pending_title is not None:
            self._assign_title(self._pending_title, line, role, page_number)
            return
        if role:
            self._start_named_section(role, line, page_number)
            return
        if self._pending_title is not None and _looks_like_title(line):
            self._assign_title(self._pending_title, line, None, page_number)
            return
        self._pending_title = None

        if _MALFORMED_MARKER_RE.match(line):
            self._start_malformed_section(line, page_number)
            return
        if self._active is self._root:
            self._active = self._new_unstructured(self._root, page_number)
        self._append(self._active, line, page_number)

    def _start_document_section(self, raw_type: str, line: str, page_number: int) -> None:
        section_type = raw_type.casefold()
        parent = (
            self._memutuskan if section_type == "menetapkan" and self._memutuskan else self._root
        )
        node = self._new_node(section_type, raw_type.title(), parent, page_number)
        if section_type == "memutuskan":
            self._memutuskan = node
        self._scope = node
        self._reset_hierarchy()
        self._active = node
        self._pending_title = None
        self._append(node, line, page_number)

    def _start_scope(
        self,
        section_type: str,
        identifier: str,
        line: str,
        page_number: int,
    ) -> None:
        node = self._new_node(section_type, identifier, self._root, page_number)
        self._in_body = True
        self._amendment_scope = None
        self._pending_amendment_target = False
        self._scope = node
        self._reset_hierarchy()
        self._active = node
        self._pending_title = None
        self._append(node, line, page_number)

    def _start_bab(self, match: re.Match[str], line: str, page_number: int) -> None:
        self._in_body = True
        self._scope = self._hierarchy_scope()
        label = f"BAB {match.group(1).upper()}"
        title = _optional_text(match.group(2))
        self._chapter = self._new_node("bab", label, self._scope, page_number, title=title)
        self._bagian = self._paragraf = self._pasal = self._ayat = None
        self._active = self._chapter
        self._pending_title = self._chapter if title is None else None
        self._append(self._chapter, line, page_number)

    def _start_bagian(self, match: re.Match[str], line: str, page_number: int) -> None:
        label = f"Bagian {match.group(1)}"
        title = _optional_text(match.group(2))
        parent = self._chapter or self._hierarchy_scope()
        self._bagian = self._new_node("bagian", label, parent, page_number, title=title)
        self._paragraf = self._pasal = self._ayat = None
        self._active = self._bagian
        self._pending_title = self._bagian if title is None else None
        self._append(self._bagian, line, page_number)

    def _start_paragraf(self, match: re.Match[str], line: str, page_number: int) -> None:
        label = f"Paragraf {match.group(1).upper()}"
        title = _optional_text(match.group(2))
        parent = self._bagian or self._chapter or self._hierarchy_scope()
        self._paragraf = self._new_node("paragraf", label, parent, page_number, title=title)
        self._pasal = self._ayat = None
        self._active = self._paragraf
        self._pending_title = self._paragraf if title is None else None
        self._append(self._paragraf, line, page_number)

    def _start_pasal(self, match: re.Match[str], line: str, page_number: int) -> None:
        self._in_body = True
        identifier = re.sub(r"\s+", "", match.group(1)).upper().replace("O", "0")
        label = f"Pasal {identifier}"
        amendment_owner = _AMENDMENT_OWNER_RE.search(f"{line} {self._lookahead}")
        explanation_owner = self._scope.type == "penjelasan" and re.search(
            r"\bAngka\s*\d+\b", self._lookahead, re.I
        )
        amendment_owner = amendment_owner or explanation_owner
        quoted_target = self._pending_amendment_target and not amendment_owner
        if amendment_owner:
            self._amendment_scope = None
            self._pending_amendment_target = False
        elif not quoted_target:
            # A normal article after an amendment block begins a new legal
            # scope. Do not allow a previous block to leak into it.
            self._amendment_scope = None
        parent = self._paragraf or self._bagian or self._chapter or self._hierarchy_scope()
        self._pasal = self._new_node("pasal", label, parent, page_number)
        self._pasal.amendment_scope = self._amendment_scope if quoted_target else None
        if amendment_owner:
            # The quoted Pasal below amend a different regulation; the parent
            # enactment article is the explicit scope boundary, not a new file.
            self._amendment_scope = self._pasal.node_id
            # The enacting article is also part of that explicit scope. This
            # prevents two independent amendment blocks with the same Pasal
            # number from being mistaken for duplicate provisions.
            self._pasal.amendment_scope = self._pasal.node_id
            self._pending_amendment_target = True
        elif quoted_target:
            self._pending_amendment_target = False
        self._ayat = None
        self._active = self._pasal
        self._pending_title = None
        self._append(self._pasal, line, page_number)

    def _start_ayat(self, match: re.Match[str], line: str, page_number: int) -> None:
        label = f"Ayat ({match.group(1).upper()})"
        parent = (
            self._pasal
            or self._paragraf
            or self._bagian
            or self._chapter
            or self._hierarchy_scope()
        )
        self._ayat = self._new_node("ayat", label, parent, page_number)
        self._active = self._ayat
        self._pending_title = None
        self._append(self._ayat, line, page_number)

    def _start_named_section(self, role: str, line: str, page_number: int) -> None:
        parent = self._chapter or self._hierarchy_scope()
        node = self._new_node(role, line, parent, page_number, title=line, role=role)
        self._bagian = self._paragraf = self._pasal = self._ayat = None
        self._active = node
        self._pending_title = None
        self._append(node, line, page_number)

    def _start_malformed_section(self, line: str, page_number: int) -> None:
        lowered = line.casefold()
        if lowered.startswith("bab"):
            self._chapter = self._bagian = self._paragraf = self._pasal = self._ayat = None
            parent = self._hierarchy_scope()
        elif lowered.startswith("bagian"):
            self._bagian = self._paragraf = self._pasal = self._ayat = None
            parent = self._chapter or self._hierarchy_scope()
        elif lowered.startswith("paragraf"):
            self._paragraf = self._pasal = self._ayat = None
            parent = self._bagian or self._chapter or self._hierarchy_scope()
        else:
            self._pasal = self._ayat = None
            parent = self._paragraf or self._bagian or self._chapter or self._hierarchy_scope()
        self._active = self._new_unstructured(parent, page_number)
        self._append(self._active, line, page_number)

    def _assign_title(
        self,
        node: _Node,
        title: str,
        role: str | None,
        page_number: int,
    ) -> None:
        node.title = f"{node.title} {title}" if node.title else title
        node.role = role
        self._active = node
        self._pending_title = node
        self._append(node, title, page_number)

    def _new_unstructured(self, parent: _Node, page_number: int) -> _Node:
        self._unstructured_count += 1
        return self._new_node(
            "unstructured",
            f"Unstructured {self._unstructured_count}",
            parent,
            page_number,
        )

    def _new_node(
        self,
        section_type: str,
        identifier: str,
        parent: _Node | None,
        page_number: int,
        *,
        title: str | None = None,
        role: str | None = None,
    ) -> _Node:
        order = self._next_order
        node = _Node(
            type=section_type,
            identifier=identifier,
            node_id=f"{self._document_id}:legal:{order:05d}",
            order=order,
            parent=parent,
            title=title,
            role=role or _role_for_title(title),
            page_start=page_number,
            page_end=page_number,
        )
        self._next_order += 1
        self._nodes.append(node)
        if parent is not None:
            parent.children.append(node)
        return node

    def _append(self, node: _Node, line: str, page_number: int) -> None:
        current: _Node | None = node
        while current is not None:
            current.parts.append((page_number, line))
            current.page_start = min(current.page_start or page_number, page_number)
            current.page_end = max(current.page_end or page_number, page_number)
            current = current.parent

    def _reset_hierarchy(self) -> None:
        self._chapter = self._bagian = self._paragraf = self._pasal = self._ayat = None

    def _hierarchy_scope(self) -> _Node:
        if self._scope.type in {"penjelasan", "lampiran"}:
            return self._scope
        return self._root

    @staticmethod
    def _freeze(node: _Node) -> LegalSection:
        if node.page_start is None or node.page_end is None:
            raise ValueError(f"Legal node {node.node_id} has no page provenance")
        return LegalSection(
            type=node.type,
            identifier=node.identifier,
            title=node.title,
            text="\n".join(text for _, text in node.parts),
            page_start=node.page_start,
            page_end=node.page_end,
            parent=node.parent.node_id if node.parent else None,
            children=tuple(child.node_id for child in node.children),
            order=node.order,
            node_id=node.node_id,
            role=node.role,
            amendment_scope=node.amendment_scope,
        )


def parse_legal_sections(
    document_id: str,
    pages: Sequence[Page],
    *,
    document_title: str | None = None,
) -> list[LegalSection]:
    """Convenience entry point for the deterministic structure parser."""
    return IndonesianLegalStructureParser().parse(
        document_id,
        pages,
        document_title=document_title,
    )


def _canonical_label(line: str) -> str:
    return " ".join(line.casefold().split()).rstrip(":")


def _optional_text(value: str | None) -> str | None:
    text = value.strip() if value else ""
    return text or None


def _role_for_title(title: str | None) -> str | None:
    return _NAMED_ROLES.get(_canonical_label(title)) if title else None


def _looks_like_title(line: str) -> bool:
    if line.endswith((".", ";", ":")):
        return False
    words = [word.strip("(),.-") for word in line.split() if word.strip("(),.-")]
    if not words or len(words) > 12:
        return False
    if line.upper() == line:
        return True
    return all(
        word.casefold() in _TITLE_CONNECTORS or not word[:1].isalpha() or word[:1].isupper()
        for word in words
    )


def _mark_source_duplicates(sections: list[LegalSection]) -> list[LegalSection]:
    """Mark exact repeated official provisions without deleting their evidence.

    A printed repeat is not a parser error. It remains a distinct node with its
    own page provenance, linked to the first occurrence in the same legal
    scope. The chunker can then omit only the redundant retrieval vector.
    """
    # A single repeated heading is ambiguous and must remain an evaluator
    # error. Classify a source duplicate only when two consecutive Pasal nodes
    # repeat an earlier consecutive pair under the same parent/scope. This
    # captures printed sequences such as UU 2/2004 Pasal 80--81 while keeping
    # accidental duplicated Pasal markers visible as defects.
    replacements: dict[int, LegalSection] = {}
    for current_index in range(len(sections) - 1):
        current = sections[current_index]
        following = sections[current_index + 1]
        if current.type.casefold() != "pasal" or following.type.casefold() != "pasal":
            continue
        for original_index in range(current_index):
            original = sections[original_index]
            original_following = sections[original_index + 1]
            if not (
                _same_provision(current, original)
                and _same_provision(following, original_following)
            ):
                continue
            replacements[current_index] = replace(
                current, source_duplicate_of=original.node_id
            )
            replacements[current_index + 1] = replace(
                following, source_duplicate_of=original_following.node_id
            )
            break
    return [replacements.get(index, section) for index, section in enumerate(sections)]


def _derive_implicit_amendment_scopes(sections: list[LegalSection]) -> list[LegalSection]:
    """Recover a nested amendment item when PDF layout hides its owner.

    Omnibus regulations frequently put ``N. Ketentuan Pasal ... diubah`` in
    the inclusive text of a Bagian/Paragraf rather than on a standalone owner
    Pasal. Bind the next Pasal to that exact preceding source marker. The
    generated scope is deterministic and the marker remains in the parent's
    preserved source text; it is not a guessed regulation identity.
    """
    by_id = {section.node_id: section for section in sections if section.node_id}
    positions = _direct_child_positions(sections, by_id)
    resolved: list[LegalSection] = []
    for section in sections:
        if section.type.casefold() != "pasal":
            resolved.append(section)
            continue
        # An owner carries its own explicit scope even if an earlier source
        # item happened to amend a Pasal with the same label.
        if section.amendment_scope and _AMENDMENT_OWNER_RE.search(section.text):
            resolved.append(section)
            continue
        if section.amendment_scope == section.node_id and section.type.casefold() == "pasal":
            # In Penjelasan, a repeated Pasal label followed by ``Angka 1``
            # begins a new enacting explanation block. It must not inherit
            # the preceding Angka item's scope merely because its label is
            # the same as the immediately preceding explanation.
            resolved.append(section)
            continue
        scope_owner = by_id.get(section.amendment_scope or "")
        inherited_same_identifier = bool(
            scope_owner and scope_owner.identifier.casefold() == section.identifier.casefold()
        )
        inferred_parent_scope = bool(
            section.parent
            and section.amendment_scope
            and section.amendment_scope.startswith(f"{section.parent}:amendment-item:")
        )
        if section.amendment_scope and not (inherited_same_identifier or inferred_parent_scope):
            resolved.append(section)
            continue
        scope = _implicit_scope_for(
            section,
            by_id,
            positions,
        )
        resolved.append(replace(section, amendment_scope=scope) if scope else section)
    return resolved


def _implicit_scope_for(
    section: LegalSection,
    by_id: dict[str, LegalSection],
    positions: dict[str, int],
) -> str | None:
    # Use only the direct structural parent. An inclusive root/document node
    # can contain an unrelated amendment marker hundreds of pages earlier;
    # walking ancestors would incorrectly put ordinary Pasal in that scope.
    if not section.parent:
        return None
    parent = by_id.get(section.parent)
    if parent is None:
        return None
    position = positions.get(section.node_id or "", parent.text.find(section.text))
    if position < 0:
        return None
    prefix = parent.text[:position]
    if parent.type.casefold() == "penjelasan":
        marker_index = _last_explanation_item(prefix)
        if marker_index is not None and parent.node_id:
            return f"{parent.node_id}:penjelasan-item:{marker_index}"
    marker_index = _last_amendment_boundary(prefix)
    if marker_index is not None and parent.node_id:
        return f"{parent.node_id}:amendment-item:{marker_index}"
    return None


def _direct_child_positions(
    sections: list[LegalSection],
    by_id: dict[str, LegalSection],
) -> dict[str, int]:
    """Resolve repeated child text to its ordered occurrence in parent text."""
    cursors: dict[str, int] = {}
    positions: dict[str, int] = {}
    for section in sections:
        if not section.node_id or not section.parent:
            continue
        parent = by_id.get(section.parent)
        if parent is None:
            continue
        start = cursors.get(parent.node_id or "", 0)
        position = parent.text.find(section.text, start)
        if position < 0:
            continue
        positions[section.node_id] = position
        cursors[parent.node_id or ""] = position + len(section.text)
    return positions


def _last_amendment_boundary(prefix: str) -> int | None:
    marker_index: int | None = None
    for index, line in enumerate(prefix.splitlines(), start=1):
        if _AMENDMENT_BOUNDARY_RE.match(line.strip()):
            marker_index = index
    return marker_index


def _last_explanation_item(prefix: str) -> int | None:
    marker_index: int | None = None
    for index, line in enumerate(prefix.splitlines(), start=1):
        if re.match(r"^Angka\s*\d+\b", line.strip(), re.IGNORECASE):
            marker_index = index
    return marker_index


def _same_provision(left: LegalSection, right: LegalSection) -> bool:
    return (
        left.parent == right.parent
        and left.type.casefold() == right.type.casefold()
        and left.identifier.casefold() == right.identifier.casefold()
        and (left.amendment_scope or "") == (right.amendment_scope or "")
        and _normalized_section_text(left.text) == _normalized_section_text(right.text)
    )


def _normalized_section_text(text: str) -> str:
    return " ".join(text.split()).casefold()
