"""
Update product descriptions: merge per-variant measurement tables across a
model group so every card lists measurements for ALL sizes in the group.

Source: SalesDrive YML feed.
Output: xlsx (update_rs_descr_<date>.xlsx) with columns for SalesDrive import:
    ID товару/послуги | SKU | Опис | Опис (UA)

Only rows whose description actually changes are included.
"""
from __future__ import annotations

import difflib
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd

from app.utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

# "Заміри" (UA) or "Замеры" (RU) heading
_HEAD = re.compile(r"(Замі?ри|Замеры)", re.IGNORECASE)
# size token like "XS", "M", "2XL", "XS-S", "46" followed by "(value)"
_PAIR = re.compile(r"([0-9A-Za-zА-Яа-яІіЇїЄє]+(?:-[0-9A-Za-zА-Яа-яІіЇїЄє]+)?)\s*\(\s*([^)]*?)\s*\)")
# a measurement line: "- Label: <values...>" up to the next "- Label:" or end
_LINE = re.compile(
    r"-\s*([^:<\n]+?)\s*:\s*(.*?)(?=(?:<[^>]*>|\s)*-\s*[^:<\n]+?\s*:|$)",
    re.S,
)

_SIZE_ORDER = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL", "7XL"]


def _extract_model(article: str) -> str:
    return article.split("_")[0].strip() if article else ""


def _size_key(token: str):
    first = token.split("-")[0].strip().upper()
    if first in _SIZE_ORDER:
        return (0, _SIZE_ORDER.index(first), token)
    if first.isdigit():
        return (1, int(first), token)
    return (2, 0, first)


def _norm_label(label: str) -> str:
    return re.sub(r"[^а-яіїєa-z]", "", label.lower())


def _split_measurements(desc: str) -> tuple[str, str | None]:
    """Return (intro_html, heading_word). intro keeps original HTML untouched."""
    m = _HEAD.search(desc)
    if not m:
        return desc, None
    head_word = m.group(1)
    # Cut at the opening of the <div>/<p> element that wraps the heading
    before = desc[: m.start()]
    cut = max(before.rfind("<div"), before.rfind("<p"), before.rfind("<P"), before.rfind("<DIV"))
    if cut < 0:
        cut = m.start()
    return desc[:cut], head_word


def _parse_table(desc: str) -> "OrderedDict[str, OrderedDict[str, str]]":
    """Parse {label: {size_token: value}} from the measurement region of a description."""
    m = _HEAD.search(desc)
    if not m:
        return OrderedDict()
    tail = desc[m.end():]
    text = re.sub(r"<[^>]+>", "\n", tail).replace("&nbsp;", " ")
    table: "OrderedDict[str, OrderedDict[str, str]]" = OrderedDict()
    for label, values in _LINE.findall(text):
        label = label.strip(" \t-•")
        pairs = _PAIR.findall(values)
        if not label or not pairs:
            continue
        bucket = table.setdefault(label, OrderedDict())
        for token, value in pairs:
            token = token.strip().upper()
            value = value.strip()
            if value:
                bucket.setdefault(token, value)
    return table


def _global_label_freq(all_descs: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for desc in all_descs:
        for label in _parse_table(desc).keys():
            counts[label] += 1
    return counts


_SIMILAR = 0.90  # only merge near-identical labels (typos), not different ones


def _merge_group(
    descs: list[str],
    freq: dict[str, int],
) -> "OrderedDict[str, OrderedDict[str, str]]":
    """
    Merge measurement tables of one model group.

    Labels are clustered only WITHIN the group (so unrelated labels in other
    groups are never merged). When typo variants cluster together, the canonical
    spelling is the one with the highest global frequency.
    """
    parsed = [_parse_table(d) for d in descs]

    # Collect raw labels with first-appearance order
    first_seen: dict[str, int] = {}
    order = 0
    for table in parsed:
        for label in table.keys():
            if label not in first_seen:
                first_seen[label] = order
                order += 1

    # Cluster raw labels (process by global freq desc so canonical = most common)
    raw_labels = sorted(first_seen, key=lambda l: (-freq.get(l, 0), first_seen[l]))
    cluster_head: dict[str, str] = {}      # canonical_norm -> canonical_spelling
    cluster_norms: list[str] = []
    raw_to_canon: dict[str, str] = {}
    for label in raw_labels:
        norm = _norm_label(label)
        match = None
        for cnorm in cluster_norms:
            if cnorm == norm or difflib.SequenceMatcher(None, cnorm, norm).ratio() >= _SIMILAR:
                match = cnorm
                break
        if match is None:
            cluster_norms.append(norm)
            cluster_head[norm] = label
            raw_to_canon[label] = label
        else:
            raw_to_canon[label] = cluster_head[match]

    # Merge values under canonical labels, ordered by first appearance
    merged: "OrderedDict[str, OrderedDict[str, str]]" = OrderedDict()
    canon_order = sorted(
        {raw_to_canon[l] for l in first_seen},
        key=lambda c: first_seen[c],
    )
    for canon in canon_order:
        merged[canon] = OrderedDict()
    for table in parsed:
        for label, sizes in table.items():
            bucket = merged[raw_to_canon[label]]
            for token, value in sizes.items():
                bucket.setdefault(token, value)
    return merged


def _render_block(merged: "OrderedDict[str, OrderedDict[str, str]]", head_word: str) -> str:
    if not merged:
        return ""
    lines = [f"{head_word}:"]
    for label, sizes in merged.items():
        tokens = sorted(sizes.keys(), key=_size_key)
        parts = ", ".join(f"{t} ({sizes[t]})" for t in tokens)
        lines.append(f"- {label}: {parts}")
    body = "<br />".join(lines)
    return f"<div><br />{body}</div>"


def _rebuild(desc: str, merged: "OrderedDict[str, OrderedDict[str, str]]", default_head: str) -> str:
    if not merged:
        return desc
    intro, head_word = _split_measurements(desc)
    head_word = head_word or default_head
    block = _render_block(merged, head_word)
    intro = intro.rstrip()
    return f"{intro}\n{block}"


def _load_offers(content: bytes) -> list[ET.Element]:
    root = ET.fromstring(content)
    shop = root.find("shop") or root
    return shop.findall(".//offer")


def generate_descriptions_file(
    output_path: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, int]:
    _progress = on_progress or (lambda _: None)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_path is None:
        output_path = settings.temp_dir / f"update_rs_descr_{ts}.xlsx"

    if settings.USE_MOCKS:
        _progress("[MOCK] Описи: тестовий режим, фід не завантажується.")
        df = pd.DataFrame(
            [{
                "ID товару/послуги": "26.2623_black_40(XS)-42(S)",
                "SKU": "26.2623_black_40(XS)-42(S)",
                "Опис": "<div>...intro...</div>\n<div><br />Замеры:<br />- Обхват груди: XS-S (102), M-L (106), L-XL (112), 2XL-3XL (116)</div>",
                "Опис (UA)": "<div>...вступ...</div>\n<div><br />Заміри:<br />- Обхват грудей: XS-S (102), M-L (106), L-XL (112), 2XL-3XL (116)</div>",
            }]
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Описи")
        return output_path, len(df)

    if not settings.SALESDRIVE_YML_URL:
        raise ValueError("SALESDRIVE_YML_URL не налаштовано")

    _progress("[1/4] Завантажую YML фід з SalesDrive...")
    resp = httpx.get(settings.SALESDRIVE_YML_URL, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    offers = _load_offers(resp.content)

    _progress(f"[2/4] Групую {len(offers)} товарів по моделях...")
    groups: "dict[str, list[ET.Element]]" = defaultdict(list)
    for offer in offers:
        article = offer.findtext("article") or offer.findtext("vendorCode") or offer.get("id", "")
        groups[_extract_model(article)].append(offer)

    all_ru = [o.findtext("description") or "" for o in offers]
    all_ua = [o.findtext("description_ua") or "" for o in offers]
    freq_ru = _global_label_freq(all_ru)
    freq_ua = _global_label_freq(all_ua)

    _progress(f"[3/4] Аналізую заміри у {len(groups)} групах...")
    rows: list[dict] = []
    for model, items in groups.items():
        ru_descs = [o.findtext("description") or "" for o in items]
        ua_descs = [o.findtext("description_ua") or "" for o in items]
        merged_ru = _merge_group(ru_descs, freq_ru)
        merged_ua = _merge_group(ua_descs, freq_ua)
        if not merged_ru and not merged_ua:
            continue

        for offer in items:
            article = offer.findtext("article") or offer.findtext("vendorCode") or offer.get("id", "")
            old_ru = offer.findtext("description") or ""
            old_ua = offer.findtext("description_ua") or ""
            new_ru = _rebuild(old_ru, merged_ru, "Замеры")
            new_ua = _rebuild(old_ua, merged_ua, "Заміри")
            if new_ru == old_ru and new_ua == old_ua:
                continue
            rows.append({
                "ID товару/послуги": article,
                "SKU": article,
                "Опис": new_ru,
                "Опис (UA)": new_ua,
            })

    rows.sort(key=lambda r: str(r.get("SKU", "")))
    _progress(f"[4/4] Записую Excel ({len(rows)} рядків)...")
    df = pd.DataFrame(rows, columns=["ID товару/послуги", "SKU", "Опис", "Опис (UA)"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Описи")

    logger.info("Descriptions file saved: %s (%d rows)", output_path, len(rows))
    return output_path, len(rows)
