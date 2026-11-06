"""Pure defect form validation and presentation; no requests, SQL or writes."""


class DefectFormError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def defect_update_payload(previous, form, now):
    description = (form.get("description") or "").strip()
    comment = (form.get("defect_comment") or "").strip()
    if not description or len(description) > 255 or len(comment) > 255:
        raise DefectFormError("Beschrieb erforderlich; Beschrieb und Bemerkung maximal 255 Zeichen.")
    try:
        priority = int(form.get("priority") or 0)
        body_id = int(form.get("body_id") or -1)
        person_id = int(form.get("person_id") or -1)
    except (TypeError, ValueError) as exc:
        raise DefectFormError("Ungültige Eingabe.") from exc
    if priority not in {0, 1, 2, 3} or body_id not in {-1, 1, 2, 3} or person_id < -1:
        raise DefectFormError("Ungültige Dringlichkeit oder Zuständigkeit.")
    if priority == 2 and (body_id < 1 or person_id < 1):
        raise DefectFormError("Bei Dringlichkeit B sind Zuständigkeit und Person erforderlich.")
    done = form.get("done") == "on"
    payload = {
        "tid": previous["tid"], "playdeviceFid": previous["playdevice_fid"],
        "expectedVersion": form.get("record_version") or None,
        "defectDescription": description, "defectComment": comment,
        "priority": priority, "defectsResponsibleBodyId": body_id,
        "responsibleUserFid": person_id,
        "assignmentStatus": previous.get("assignment_status") or "",
        "dateAssignmentCreated": (previous.get("assignment_created").isoformat()
                                   if previous.get("assignment_created") else None),
        "assignmentComment": previous.get("assignment_comment") or "",
        "dateDone": ((previous.get("date_done") or now).isoformat()
                     if done else None),
    }
    return payload


def defect_edit_context(data, users, form_values=None):
    data = dict(data)
    if form_values is not None:
        data.update(defectDescription=form_values.get("description", ""),
                    defectComment=form_values.get("defect_comment", ""),
                    done=form_values.get("done") == "on")
        for key, field in (("priority", "priority"), ("defectsResponsibleBodyId", "body_id"), ("responsibleUserFid", "person_id")):
            try:
                data[key] = int(form_values.get(field) or -1)
            except (ValueError, TypeError):
                pass
    assigned_user = next((u for u in users if u["fid"] == data["responsibleUserFid"]), None)
    if assigned_user:
        assigned_name = " ".join(filter(None, [assigned_user.get("first_name"), assigned_user.get("last_name")]))
    else:
        assigned_name = "Nicht zugewiesen" if data["responsibleUserFid"] < 1 else f"FID {data['responsibleUserFid']}"
    return {"defect": data, "users": users, "assigned_name": assigned_name,
            "inactive_assignee": data["responsibleUserFid"] > 0 and not assigned_user}
