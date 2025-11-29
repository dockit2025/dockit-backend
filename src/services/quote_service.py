from typing import Dict, Any, List, Optional

from sqlmodel import Session, select

from src.server.models import Quote, QuoteLine, Customer
from src.server.schemas.quote import QuoteDraftIn, MaterialDraftIn

# Fri text-tolkning
from free_text_interpreter import interpret_free_text

# ROT-beräkning
from src.rot_calculator import RotConfig, apply_rot_to_lines
from src.services.atl_lookup import get_atl_time_minutes
from src.services.atl_lookup import get_atl_time_minutes

# Prislogik
from src.services.pricing import get_price
from src.services.work_profiles import load_work_profiles

# Standardtimpris för arbete (kan ändras på ett ställe)
DEFAULT_HOURLY_RATE = 800.0


def _get_hourly_rate(payload: QuoteDraftIn) -> float:
    """
    Hämtar timpris för arbete.

    Logik:
      1) Om payload.hourly_rate finns och är > 0 → använd det.
      2) Annars använd DEFAULT_HOURLY_RATE.
    """
    rate = getattr(payload, "hourly_rate", None)
    try:
        rate_f = float(rate)
        if rate_f > 0:
            return rate_f
    except (TypeError, ValueError):
        pass
    return DEFAULT_HOURLY_RATE


def _calc_totals(payload: QuoteDraftIn) -> Dict[str, float]:
    """
    Enkel beräkning av subtotal, ROT och total utifrån payload.lines.

    Används i create_quote (där raderna redan är satta från frontend).
    Här gör vi ännu ingen ROT-beräkning – den sköts i make_draft-flödet.
    """
    subtotal = 0.0
    for l in payload.lines:
        qty = float(getattr(l, "qty", 0) or 0)
        price = float(getattr(l, "unit_price_sek", 0) or 0)
        subtotal += qty * price

    rot_discount = 0.0
    total = subtotal - rot_discount

    return {
        "subtotal": subtotal,
        "rot_discount": rot_discount,
        "total": total,
    }


def _build_lines_from_payload(payload: QuoteDraftIn) -> List[Dict[str, Any]]:
    """
    Bygger upp radstrukturen (lines) från befintligt payload.lines,
    i samma struktur som make_draft använder internt.
    """
    out_lines: List[Dict[str, Any]] = []
    for l in payload.lines:
        qty = float(getattr(l, "qty", 0) or 0)
        price = float(getattr(l, "unit_price_sek", 0) or 0)
        out_lines.append(
            {
                "kind": getattr(l, "kind", None),
                "ref": getattr(l, "ref", None),
                "description": getattr(l, "description", None),
                "qty": qty,
                "unit_price_sek": price,
                "line_total_sek": qty * price,
            }
        )
    return out_lines


def _format_description(label: str, text_segment: Any) -> str:
    """
    Gör om text till offert-snygg beskrivning.

    Regler:
      - "byta ..."       → "Byte av ..."
      - "installera ..." → "Installation av ..."
      - "montera ..."    → "Montering av ..."
      - "sätta upp ..."  → "Montering av ..."

      Interna fraser:
      - "och installera ..." → "och installation av ..."
      - "och sätta upp ..."  → "och montering av ..."

      Först försöker vi med kundens text_segment.
      Om det inte funkar används taskens label.
    """
    def transform(phrase: str) -> str:
        p = phrase.strip()
        if not p:
            return ""

        lower = p.lower()

        # Verb i början
        if lower.startswith("byta "):
            tail = p[5:].lstrip()
            p = f"Byte av {tail}"
            lower = p.lower()
        elif lower.startswith("installera "):
            tail = p[11:].lstrip()
            p = f"Installation av {tail}"
            lower = p.lower()
        elif lower.startswith("montera "):
            tail = p[8:].lstrip()
            p = f"Montering av {tail}"
            lower = p.lower()
        elif lower.startswith("sätta upp "):
            tail = p[9:].lstrip()
            p = f"Montering av {tail}"
            lower = p.lower()

        # Hjälpfunktion för att byta interna fraser utan att tappa resten av texten
        def replace_inner(source: str, find: str, replacement: str) -> str:
            s_lower = source.lower()
            idx = s_lower.find(find)
            if idx == -1:
                return source
            tail = source[idx + len(find):].lstrip()
            # Behåll allt före frasen, lägg till replacement och sedan tail
            return source[:idx] + replacement + " " + tail

        # "och installera ..." → "och installation av ..."
        p = replace_inner(p, " och installera ", " och installation av")
        # "och sätta upp ..." → "och montering av ..."
        p = replace_inner(p, " och sätta upp ", " och montering av")

        # Se till att första bokstaven är versal
        if p:
            p = p[0].upper() + p[1:]

        return p

    # 1) Försök forma om kundens textsegment
    if isinstance(text_segment, str) and text_segment.strip():
        transformed = transform(text_segment)
        if transformed:
            return transformed

    # 2) Fallback: använd label
    if isinstance(label, str) and label.strip():
        transformed = transform(label)
        if transformed:
            return transformed

    return "Arbetsmoment"


def _build_work_lines_from_interpretation(
    interpretation: Dict[str, Any],
    hourly_rate: float,
) -> List[Dict[str, Any]]:
    """
    Bygger automatiska arbetsrader (work) baserat på interpretation.tasks.
    """
    tasks = interpretation.get("tasks") or []
    lines: List[Dict[str, Any]] = []

    for t in tasks:
        time_minutes_total = float(t.get("time_minutes_total", 0) or 0)
        quantity_units = float(t.get("quantity", 0) or 0)

        qty_hours = time_minutes_total / 60.0 if time_minutes_total > 0 else 0.0

        if qty_hours > 0:
            qty = qty_hours
        elif quantity_units > 0:
            qty = quantity_units
        else:
            qty = 1.0

        label = t.get("label") or t.get("task_id") or "Arbetsmoment"
        text_segment = t.get("text_segment") or ""
        description = _format_description(label, text_segment)

        line_total = qty * hourly_rate

        line = {
            "kind": "work",
            "ref": t.get("task_id"),
            "description": description,
            "qty": qty,
            "unit_price_sek": hourly_rate,
            "line_total_sek": line_total,
        }
        lines.append(line)

    return lines


def _build_material_lines_from_interpretation(
    interpretation: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Bygger materialrader (kind: "material") baserat på interpretation.tasks[].materials.

    Mappingarna anger:
      - vilka artiklar som behövs (ref, description)
      - ungefär hur många (quantity_per_unit osv.)
    Pris sätts inte här, utan via pricing.get_price.
    """
    tasks = interpretation.get("tasks") or []
    material_lines: List[Dict[str, Any]] = []

    for t in tasks:
        materials = t.get("materials") or []
        if not isinstance(materials, list):
            continue

        try:
            task_qty = float(t.get("quantity") or 1.0)
        except (TypeError, ValueError):
            task_qty = 1.0

        for m in materials:
            if not isinstance(m, dict):
                continue

            ref = (
                m.get("ref")
                or m.get("id")
                or m.get("sku")
                or m.get("article_number")
                or m.get("material_id")
            )

            desc = (
                m.get("description")
                or m.get("name")
                or m.get("label")
                or "Material"
            )

            raw_qty = m.get("quantity")
            if raw_qty is None:
                raw_qty = m.get("qty")

            per_unit = m.get("quantity_per_unit") or m.get("per_unit")

            if raw_qty is not None:
                try:
                    qty = float(raw_qty)
                except (TypeError, ValueError):
                    qty = 1.0
            elif per_unit is not None:
                try:
                    per_unit_f = float(per_unit)
                except (TypeError, ValueError):
                    per_unit_f = 1.0
                qty = per_unit_f * task_qty
            else:
                qty = task_qty if task_qty > 0 else 1.0

            unit_price = 0.0
            line_total = qty * unit_price

            line = {
                "kind": "material",
                "ref": ref,
                "description": desc,
                "qty": qty,
                "unit_price_sek": unit_price,
                "line_total_sek": line_total,
            }
            material_lines.append(line)

    return material_lines


def _apply_pricelist_to_material_lines(
    lines: List[Dict[str, Any]],
    price_lookup: Dict[str, float],
) -> None:
    """
    Legacy-funktion för prislista (ej aktiv i nya flödet).
    Ligger kvar om vi vill återanvända mönstret senare.
    """
    if not price_lookup:
        return

    for l in lines:
        if l.get("kind") != "material":
            continue

        ref = l.get("ref")
        if not ref:
            continue

        unit_price = price_lookup.get(ref)
        if unit_price is None:
            continue

        try:
            unit_price_f = float(unit_price)
        except (TypeError, ValueError):
            continue

        l["unit_price_sek"] = unit_price_f
        qty = float(l.get("qty", 0) or 0)
        l["line_total_sek"] = qty * unit_price_f


def make_draft(*, payload: QuoteDraftIn, session: Session) -> Dict[str, Any]:
    """
    Beräknar ett offertutkast baserat på inkommande data.

    Flöde:
      - Tolka job_summary (fri text) → interpretation via interpret_free_text.
      - Om payload.lines saknas:
            * skapa arbetsrader (work) från tasks
            * skapa materialrader (material) från tasks[].materials
      - Sätt timpris för arbete.
      - Sätt materialpriser via pricing.get_price.
      - Räkna subtotal, ROT och total.
    """
    # 1) Tolkning av fri text
    interpretation: Optional[Dict[str, Any]] = None

    summary_text = getattr(payload, "job_summary", None)
    if not (isinstance(summary_text, str) and summary_text.strip()):
        summary_text = getattr(payload, "free_text", None)

    if isinstance(summary_text, str) and summary_text.strip():
        interpretation = interpret_free_text(summary_text.strip())

    # 2) Timpris
    hourly_rate = _get_hourly_rate(payload)

    # 3) Bygg rader
    if payload.lines:
        out_lines = _build_lines_from_payload(payload)
    else:
        if interpretation is not None:
            work_lines = _build_work_lines_from_interpretation(interpretation, hourly_rate)
            material_lines = _build_material_lines_from_interpretation(interpretation)
            out_lines = work_lines + material_lines
        else:
            out_lines = []

    # 3b) line_type + ROT-flagga på alla rader
    for l in out_lines:
        kind = l.get("kind")
        line_type = "work" if kind == "work" else "material"
        l["line_type"] = line_type
        l["is_rot_eligible"] = line_type == "work"

    # 3c) Prislogik för materialrader
    # Använd kundens e-post som primär identitet (fallback: namn)
    customer_id: Optional[str] = (
        getattr(payload, "customer_email", None)
        or getattr(payload, "customer_name", None)
    )

    for l in out_lines:
        if l.get("kind") != "material":
            # se till att work-rader åtminstone har korrekt line_total
            qty_existing = float(l.get("qty", 0) or 0.0)
            unit_existing = float(l.get("unit_price_sek", 0) or 0.0)
            l["line_total_sek"] = qty_existing * unit_existing
            continue

        ref = l.get("ref")
        if not ref:
            unit_price_existing = float(l.get("unit_price_sek", 0) or 0.0)
            qty_existing = float(l.get("qty", 0) or 0.0)
            l["unit_price_sek"] = unit_price_existing
            l["line_total_sek"] = qty_existing * unit_price_existing
            continue

        unit_price = get_price(customer_id, str(ref))
        l["unit_price_sek"] = unit_price
        qty = float(l.get("qty", 0) or 0.0)
        l["line_total_sek"] = qty * unit_price

    # 4) Subtotal (före ROT)
    subtotal = 0.0
    for l in out_lines:
        qty = float(l.get("qty", 0) or 0)
        price = float(l.get("unit_price_sek", 0) or 0)
        subtotal += qty * price

    # 5) ROT
    rot_discount = 0.0
    rot_summary: Optional[Dict[str, Any]] = None

    if getattr(payload, "apply_rot", False):
        rot_config = RotConfig(
            rot_rate=0.30,
            max_per_person_sek=50_000,
            num_persons=1,
        )

        prepared_lines: List[Dict[str, Any]] = []
        for l in out_lines:
            line_total = float(l.get("line_total_sek", 0) or 0)
            prepared = dict(l)
            prepared["total_price_sek"] = line_total
            prepared_lines.append(prepared)

        updated_lines, rot_summary = apply_rot_to_lines(prepared_lines, rot_config)
        out_lines = updated_lines
        rot_discount = float(rot_summary.get("rot_amount_sek", 0) or 0)

    total = subtotal - rot_discount

    # 6) Tolkad arbetstid (om interpretation finns)
    interpreted_hours = 0.0
    if interpretation is not None:
        try:
            interpreted_hours = float(
                (interpretation.get("totals") or {}).get("total_time_hours", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            interpreted_hours = 0.0

    # 7) Svar till klient
    result: Dict[str, Any] = {
        "id": None,
        "title": f"Preliminär offert för {getattr(payload, 'customer_name', '')}".strip(),
        "customer_name": getattr(payload, "customer_name", None),
        "subtotal_sek": subtotal,
        "rot_discount_sek": rot_discount,
        "total_sek": total,
        "hourly_rate_sek": hourly_rate,
        "interpreted_work_hours": interpreted_hours,
        "lines": out_lines,
    }

    if rot_summary is not None:
        result["rot_summary"] = rot_summary

    if interpretation is not None:
        result["interpretation"] = interpretation

    return result


def create_quote(*, payload: QuoteDraftIn, session: Session) -> Quote:
    """
    Skapar och sparar en offert plus rader i databasen,
    baserat på samma payload-struktur som make_draft använder.
    """
    # Hämta eller skapa kund
    email = getattr(payload, "customer_email", None)
    name = getattr(payload, "customer_name", None)

    cust = None
    if email:
        cust = session.exec(select(Customer).where(Customer.email == email)).first()
    if not cust and name:
        cust = session.exec(select(Customer).where(Customer.name == name)).first()
    if not cust:
        cust = Customer(name=name, email=email)
        session.add(cust)
        session.commit()
        session.refresh(cust)

    totals = _calc_totals(payload)

    # Skapa offert
    quote = Quote(
        customer_id=cust.id if cust else None,
        title=f"Preliminär offert för {name}" if name else "Preliminär offert",
        subtotal_sek=totals["subtotal"],
        rot_discount_sek=totals["rot_discount"],
        total_sek=totals["total"],
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    # Skapa rader
    for l in payload.lines:
        qty = float(getattr(l, "qty", 0) or 0)
        price = float(getattr(l, "unit_price_sek", 0) or 0)
        ql = QuoteLine(
            quote_id=quote.id,
            kind=getattr(l, "kind", None),
            ref=getattr(l, "ref", None),
            description=getattr(l, "description", None),
            qty=qty,
            unit_price_sek=price,
            line_total_sek=qty * price,
        )
        session.add(ql)

    session.commit()
    return quote



def _estimate_task_time_minutes(task_id: str, quantity_units: float) -> float:
    """
    Enkel, hårdkodad tidsuppskattning per task-id i material-läget.
    Detta är en första version – senare kan vi koppla detta mot ATL på samma sätt
    som fri-text-tolken gör.

    quantity_units är t.ex. meter rör eller antal uttag (st).
    """
    # TODO: flytta detta till en gemensam "task_metadata"-service kopplad till ATL.
    if task_id == "dra_vp_ror_infalld_vagg":
        # Samma som i fri-text-vägen: ca 1.8 min/m
        minutes_per_unit = get_atl_time_minutes("Infällda rör (VP 16–20 mm)", 0)
    elif task_id == "lagga_kabel_i_list":
        # Vår manuella schablon: 5 min/m
        minutes_per_unit = 5.0
    elif task_id == "installera_nytt_vagguttag":
        # Manuellt: 45 min per nytt uttag
        minutes_per_unit = 45.0
    else:
        # Okänt task – ingen tid (endast material debiteras)
        minutes_per_unit = 0.0

    return quantity_units * minutes_per_unit


def _find_work_profile(material_ref: str, environment: Optional[str], work_type: Optional[str]) -> Optional[dict]:
    """
    Försöker hitta en work_profile i work_profiles.yaml som matchar
    material_ref + (ev.) environment + work_type.
    """
    profiles = load_work_profiles()

    for p in profiles:
        matches = p.get("matches") or {}
        if matches.get("material_ref") != material_ref:
            continue

        # Om environment/work_type är satta på raden, kräv matchning.
        if environment and matches.get("environment") != environment:
            continue
        if work_type and matches.get("work_type") != work_type:
            continue

        return p

    return None


def _get_task_description_for_material_mode(task_id: str) -> str:
    mapping = {
        "dra_vp_ror_infalld_vagg": "Infälld förläggning av VP-rör i vägg för eldragning.",
        "INSTALLERA-VAGGUTTAG-INFALLT": "Installation av infällt jordat vägguttag.",
        "INSTALLERA-DIMMER": "Installation av universaldimmer (ersätter befintlig strömbrytare).",
        "dra_kabelkanal_vagg": "Montering av kabelkanal på vägg för kabeldragning.",
    }
    tid = (task_id or "").strip()
    if tid in mapping:
        return mapping[tid]
    base = tid.replace("_", " ").replace("-", " ").strip()
    if not base:
        return "Arbete"
    return base[0].upper() + base[1:]


def material_draft(*, payload: MaterialDraftIn, session: Session) -> Dict[str, Any]:
    """
    Material-läge:
      - Tar emot en lista material_items (som redan tolkats av material_list_parser)
      - Bygger:
          * materialrader med pris via pricing.get_price
          * arbetsrader baserat på work_profiles + schablontider
      - Beräknar subtotal, ROT och total på samma sätt som make_draft.
    """
    # Timpris (samma logik som make_draft)
    hourly_rate = _get_hourly_rate(payload)

    # Kund-id för prislogik (som i make_draft)
    customer_id: Optional[str] = (
        getattr(payload, "customer_email", None)
        or getattr(payload, "customer_name", None)
    )

    material_items = getattr(payload, "material_items", []) or []

    out_lines: List[Dict[str, Any]] = []

    # 1) Bygg materialrader + underlag för arbetstid
    work_units_per_task: Dict[str, float] = {}

    for item in material_items:
        # item är en Pydantic-modell – använd attribut
        raw = getattr(item, "raw", "")
        qty = float(getattr(item, "qty", 0) or 0)
        unit = getattr(item, "unit", "") or ""
        material_ref = getattr(item, "material_ref", "") or ""
        environment = getattr(item, "environment", None)
        work_type = getattr(item, "work_type", None)

        # Skapa materialrad (alltid – oavsett om vi hittar work_profile)
        if material_ref:
            ref_for_pricing = material_ref
        else:
            ref_for_pricing = raw or material_ref

        unit_price = get_price(customer_id, str(ref_for_pricing)) if ref_for_pricing else 0.0
        line_total = qty * unit_price

        material_desc = raw or material_ref or "Material"

        out_lines.append(
            {
                "kind": "material",
                "ref": material_ref,
                "description": material_desc,
                "qty": qty,
                "unit_price_sek": unit_price,
                "line_total_sek": line_total,
            }
        )

        # 2) Work profiles → samla upp hur mycket arbete vi ska göra per task-id
        if not material_ref:
            continue

        profile = _find_work_profile(material_ref, environment, work_type)
        if not profile:
            # Inget kopplat arbetssätt → endast material debiteras
            continue

        tasks = profile.get("tasks") or []
        for t in tasks:
            task_id = t.get("task_id")
            if not task_id:
                continue

            per_unit = t.get("quantity_per_unit", 1.0)
            try:
                per_unit_f = float(per_unit)
            except (TypeError, ValueError):
                per_unit_f = 1.0

            units_for_task = qty * per_unit_f
            if units_for_task <= 0:
                continue

            work_units_per_task[task_id] = work_units_per_task.get(task_id, 0.0) + units_for_task

    # 3) Bygg arbetsrader baserat på work_units_per_task
    for task_id, units in work_units_per_task.items():
        time_minutes_total = _estimate_task_time_minutes(task_id, units)
        if time_minutes_total <= 0:
            # Om vi inte har någon tidsuppskattning än – hoppa över arbetsrad
            continue

        qty_hours = time_minutes_total / 60.0
        if qty_hours <= 0:
            continue

        # Beskrivning – använd task_id som enkel label tills vi vill snygga till det
        description = _get_task_description_for_material_mode(task_id)

        line_total = qty_hours * hourly_rate

        out_lines.append(
            {
                "kind": "work",
                "ref": task_id,
                "description": description,
                "qty": qty_hours,
                "unit_price_sek": hourly_rate,
                "line_total_sek": line_total,
            }
        )

    # 3b) line_type + ROT-flagga
    for l in out_lines:
        kind = l.get("kind")
        line_type = "work" if kind == "work" else "material"
        l["line_type"] = line_type
        l["is_rot_eligible"] = line_type == "work"

    # 4) Subtotal (före ROT)
    subtotal = 0.0
    for l in out_lines:
        qty = float(l.get("qty", 0) or 0)
        price = float(l.get("unit_price_sek", 0) or 0)
        subtotal += qty * price

    # 5) ROT
    rot_discount = 0.0
    rot_summary: Optional[Dict[str, Any]] = None

    if getattr(payload, "apply_rot", False):
        rot_config = RotConfig(
            rot_rate=0.30,
            max_per_person_sek=50_000,
            num_persons=1,
        )

        prepared_lines: List[Dict[str, Any]] = []
        for l in out_lines:
            line_total = float(l.get("line_total_sek", 0) or 0)
            prepared = dict(l)
            prepared["total_price_sek"] = line_total
            prepared_lines.append(prepared)

        updated_lines, rot_summary = apply_rot_to_lines(prepared_lines, rot_config)
        out_lines = updated_lines
        rot_discount = float(rot_summary.get("rot_amount_sek", 0) or 0)

    total = subtotal - rot_discount

    # 6) Tolkad arbetstid: summera alla arbetstimmar
    interpreted_hours = 0.0
    for l in out_lines:
        if l.get("kind") == "work":
            try:
                interpreted_hours += float(l.get("qty") or 0.0)
            except (TypeError, ValueError):
                continue

    # 7) Svar
    result: Dict[str, Any] = {
        "id": None,
        "title": f"Preliminär offert (material-läge) för {getattr(payload, 'customer_name', '')}".strip(),
        "customer_name": getattr(payload, "customer_name", None),
        "subtotal_sek": subtotal,
        "rot_discount_sek": rot_discount,
        "total_sek": total,
        "hourly_rate_sek": hourly_rate,
        "interpreted_work_hours": interpreted_hours,
        "lines": out_lines,
        "mode": "material",
    }

    if rot_summary is not None:
        result["rot_summary"] = rot_summary

    return result




def _estimate_task_time_minutes(task_id: str, quantity_units: float) -> float:
    """
    Tidsuppskattning per task via ATL om möjligt, annars manuella schabloner.

    quantity_units är t.ex. meter rör eller antal uttag (st).
    """
    task_id = task_id or ""
    qty = float(quantity_units or 0.0)
    if qty <= 0:
        return 0.0

    # Försök ATL först för de task-id där vi vet vilket moment som gäller
    if task_id == "dra_vp_ror_infalld_vagg":
        minutes_per_unit = get_atl_time_minutes("Infällda rör (VP 16–20 mm)", 0)
        try:
            minutes_per_unit_f = float(minutes_per_unit)
        except (TypeError, ValueError):
            minutes_per_unit_f = 0.0

        if minutes_per_unit_f > 0:
            return qty * minutes_per_unit_f

    # Fallback: manuella schabloner (samma som tidigare logik)
    if task_id in ("lagga_kabel_i_list", "dra_kabelkanal_vagg"):
        # Vår manuella schablon: 5 min/m kabel/list/kanal
        minutes_per_unit = 5.0
    elif task_id in ("installera_nytt_vagguttag", "INSTALLERA-VAGGUTTAG-INFALLT"):
        # Manuellt: 45 min per nytt infällt uttag
        minutes_per_unit = 45.0
    elif task_id == "INSTALLERA-DIMMER":
        # Rimlig schablon: ca 30 min per dimmer
        minutes_per_unit = 30.0
    else:
        # Okänt task – ingen tid (endast material debiteras)
        minutes_per_unit = 0.0

    return qty * minutes_per_unit






def _estimate_task_time_minutes(task_id: str, quantity_units: float) -> float:
    """
    Tidsuppskattning per task via ATL om möjligt, annars manuella schabloner.

    quantity_units är t.ex. meter kabel/rör eller antal apparater (st).
    """
    task_id = task_id or ""
    qty = float(quantity_units or 0.0)
    if qty <= 0:
        return 0.0

    # 1) ATL-baserat för infällda VP-rör (samma som i fri-text-läget)
    if task_id == "dra_vp_ror_infalld_vagg":
        minutes_per_unit = get_atl_time_minutes("Infällda rör (VP 16–20 mm)", 0)
        try:
            minutes_per_unit_f = float(minutes_per_unit)
        except (TypeError, ValueError):
            minutes_per_unit_f = 0.0

        if minutes_per_unit_f > 0:
            return qty * minutes_per_unit_f

    # 2) Manuella schabloner
    if task_id in ("lagga_kabel_i_list", "dra_kabelkanal_vagg"):
        # ca 5 min/m för list/kanal
        minutes_per_unit = 5.0
    elif task_id == "dra_kabel_i_ror":
        # kabel 3G1,5 i rör infällt i vägg – lite mer jobb än bara kanal
        minutes_per_unit = 6.0  # ~0,1 h/m
    elif task_id in ("installera_nytt_vagguttag", "INSTALLERA-VAGGUTTAG-INFALLT"):
        # nytt/infällt vägguttag
        minutes_per_unit = 45.0
    elif task_id == "INSTALLERA-DIMMER":
        # byte/installation av dimmer
        minutes_per_unit = 30.0
    elif task_id in ("byta_strombrytare",):
        minutes_per_unit = 30.0
    elif task_id in ("INSTALLERA-SPOTLIGHT-TAK",):
        # infälld spotlight i tak
        minutes_per_unit = 45.0
    elif task_id in ("installera-kronbrytare",):
        minutes_per_unit = 45.0
    else:
        # Okänt task – ingen tid (endast material debiteras)
        minutes_per_unit = 0.0

    return qty * minutes_per_unit

