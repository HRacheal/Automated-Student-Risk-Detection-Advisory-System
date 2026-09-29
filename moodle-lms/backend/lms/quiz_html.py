"""
Turns the question HTML that Moodle's quiz web services return into plain, structured data
(question text, answer controls, feedback). The browser never receives Moodle HTML, so no
markup from Moodle is ever injected into the page.

Supports the standard input-based question types (true/false, multiple choice single and
multiple answer, short answer, numerical, select menus, essay text). Anything else is
reported as unsupported with a link to answer it in Moodle.
"""
import re
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag


def text_of(node: Optional[Tag]) -> str:
    if node is None:
        return ""
    for hidden in node.select(".accesshide, .sr-only, script, style"):
        hidden.decompose()
    lines = [re.sub(r"[ \t\r\f\v\xa0]+", " ", line).strip() for line in node.get_text("\n").split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def html_to_text(html: Optional[str]) -> str:
    if not html:
        return ""
    return text_of(BeautifulSoup(html, "html.parser"))


def _is_flag(name: str) -> bool:
    return name.endswith(":flagged") or name.endswith("_:flagged")


def _label_for(soup: BeautifulSoup, el: Tag) -> str:
    return " ".join(_raw_label(soup, el).split())   # labels are one line


def _raw_label(soup: BeautifulSoup, el: Tag) -> str:
    el_id = el.get("id")
    if el_id:
        label = soup.find("label", attrs={"for": el_id})
        if label:
            return text_of(BeautifulSoup(str(label), "html.parser"))
    labelledby = el.get("aria-labelledby")
    if labelledby:
        parts = []
        for ref in str(labelledby).split():
            node = soup.find(id=ref)
            if node:
                parts.append(text_of(BeautifulSoup(str(node), "html.parser")))
        if parts:
            return " ".join(p for p in parts if p)
    parent = el.parent
    if parent is not None:
        return text_of(BeautifulSoup(str(parent), "html.parser"))
    return str(el.get("value", ""))


def parse_question(q: dict[str, Any]) -> dict[str, Any]:
    """q is one entry of mod_quiz_get_attempt_data / get_attempt_review 'questions'."""
    soup = BeautifulSoup(q.get("html") or "", "html.parser")
    formulation = soup.select_one(".formulation") or soup

    hidden: dict[str, str] = {}
    fields: list[dict[str, Any]] = []
    radios: dict[str, dict[str, Any]] = {}
    readonly = False

    for el in formulation.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name or _is_flag(name):
            continue
        disabled = el.has_attr("disabled") or el.has_attr("readonly")
        readonly = readonly or disabled
        if el.name == "select":
            options = [{"value": o.get("value", ""), "label": text_of(BeautifulSoup(str(o), "html.parser"))}
                       for o in el.find_all("option")]
            selected = el.find("option", selected=True)
            fields.append({"kind": "select", "name": name, "label": _label_for(soup, el),
                           "options": options, "value": selected.get("value", "") if selected else ""})
            continue
        if el.name == "textarea":
            fields.append({"kind": "textarea", "name": name, "label": _label_for(soup, el),
                           "value": el.get_text() or ""})
            continue
        kind = (el.get("type") or "text").lower()
        value = el.get("value", "")
        if kind == "hidden":
            hidden[name] = value
        elif kind == "radio":
            group = radios.get(name)
            if group is None:
                group = {"kind": "radio", "name": name, "options": [], "value": None}
                radios[name] = group
                fields.append(group)
            label = _label_for(soup, el)
            group["options"].append({"value": value, "label": label})
            if el.has_attr("checked"):
                group["value"] = value
        elif kind == "checkbox":
            fields.append({"kind": "checkbox", "name": name, "label": _label_for(soup, el),
                           "value": value, "checked": el.has_attr("checked")})
        elif kind in {"text", "number"}:
            fields.append({"kind": "text", "name": name, "label": _label_for(soup, el), "value": value})
        # buttons / submit / file inputs are not part of the answer

    # "Clear my choice" is a real option (value -1) but reads better as an action
    for group in radios.values():
        group["options"] = [o for o in group["options"] if o["value"] != "-1" or o["label"]]

    info = soup.select_one(".info")
    outcome = soup.select_one(".outcome")
    feedback = {
        "specific": text_of(soup.select_one(".specificfeedback")),
        "general": text_of(soup.select_one(".generalfeedback")),
        "right_answer": text_of(soup.select_one(".rightanswer")),
        "outcome": text_of(outcome) if outcome else "",
    }
    return {
        "slot": q.get("slot"),
        "page": q.get("page"),
        "number": q.get("questionnumber") or q.get("number") or (text_of(info.select_one(".qno")) if info else None),
        "type": q.get("type"),
        "status": q.get("status") or (text_of(info.select_one(".state")) if info else ""),
        "state_class": q.get("stateclass"),
        "mark": q.get("mark"),
        "max_mark": q.get("maxmark"),
        "text": text_of(soup.select_one(".qtext")),
        "fields": fields,
        "hidden": hidden,
        "readonly": readonly,
        "supported": bool(fields) or q.get("type") == "description",
        "feedback": {k: v for k, v in feedback.items() if v},
    }


def build_submission(questions: list[dict[str, Any]], answers: dict[str, Any]) -> list[dict[str, str]]:
    """Builds the name/value list for mod_quiz_process_attempt from Moodle's own hidden fields
    (sequence checks) plus the student's answers - but ONLY for field names Moodle rendered on
    this page, so a request can never write to another question or slot."""
    data: dict[str, str] = {}
    allowed: set[str] = set()
    for q in questions:
        data.update(q["hidden"])
        for f in q["fields"]:
            allowed.add(f["name"])
            if f["kind"] == "checkbox" and f["name"] not in q["hidden"]:
                data.setdefault(f["name"], "0")
    for name, value in (answers or {}).items():
        if name in allowed and value is not None:
            data[name] = str(value)
    # Tells Moodle's question engine exactly which questions this page covers.
    data["slots"] = ",".join(str(q["slot"]) for q in questions if q.get("slot") is not None)
    return [{"name": k, "value": v} for k, v in data.items()]


# Finishing from the summary page processes no question (like Moodle's own "Submit all and
# finish" button), so answers saved earlier are kept exactly as they are.
FINISH_ONLY = [{"name": "slots", "value": ""}]
