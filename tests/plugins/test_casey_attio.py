"""casey_attio: fv_*-only writes with type normalization, flattening, notes, tasks, no delete surface."""

import json

import pytest


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ATTIO_API_KEY", "attio-key")
    import plugins.casey_attio as plugin
    from plugins.casey_attio import client

    calls = []
    attrs = {"people": [
        {"api_slug": "fv_partner_status", "type": "status"},
        {"api_slug": "fv_vertical", "type": "select"},
        {"api_slug": "fv_mtd_commission", "type": "currency"},
        {"api_slug": "fv_channel_lead", "type": "record-reference",
         "config": {"record_reference": {"allowed_objects": [{"api_slug": "people"}]}}},
        {"api_slug": "fv_active_practices", "type": "number"},
        {"api_slug": "fv_next_action", "type": "text"},
        {"api_slug": "fv_next_action_due", "type": "date"},
        {"api_slug": "name", "type": "personal-name"},
    ]}

    def fake(method, url, *, headers=None, body=None, timeout=15):
        calls.append({"method": method, "url": url, "body": body})
        assert headers["Authorization"] == "Bearer attio-key"
        if "/attributes" in url:
            return {"data": attrs["people"]}
        if url.endswith("/records/query"):
            return {"data": [{"id": {"record_id": "rec-1", "object_id": "people"}, "values": {
                "name": [{"full_name": "Dana Partner"}],
                "email_addresses": [{"email_address": "dana@x.com"}],
                "fv_role": [{"option": {"title": "Pathway Partner"}}],
                "fv_partner_status": [{"status": {"title": "Qualified"}}],
                "fv_mtd_commission": [{"currency_value": 45.0}],
                "fv_channel_lead": [{"target_object": "people", "target_record_id": "kirk-1"}]}}]}
        if method == "PATCH" and "/records/" in url:
            return {"data": {"id": {"record_id": "rec-1"}, "values": body["data"]["values"]}}
        if url.endswith("/notes"):
            return {"data": {"id": {"note_id": "n1"}}}
        if url.endswith("/tasks") and method == "POST":
            return {"data": {"id": {"task_id": "t1"}}}
        if "/tasks?" in url:
            return {"data": [{"id": {"task_id": "t1"}, "content_plaintext": "Reach out", "deadline_at": None,
                              "created_at": "2026-11-14T10:00:00Z", "linked_records": []}]}
        if method == "PATCH" and "/tasks/" in url:
            return {"data": {}}
        raise AssertionError(url)

    monkeypatch.setattr(client, "http_json", fake)
    client._ATTR_CACHE.clear()
    return plugin, client, calls


def test_find_person_flattens(env):
    plugin, client, calls = env
    out = json.loads(plugin.h_find_person({"email": "Dana@X.com"}))
    assert out["success"]
    p = out["people"][0]
    assert p["record_id"] == "rec-1" and p["name"] == "Dana Partner" and p["fv_role"] == "Pathway Partner"
    assert p["fv_partner_status"] == "Qualified" and p["fv_mtd_commission"] == 45.0
    assert p["fv_channel_lead"] == {"object": "people", "record_id": "kirk-1"}
    assert calls[-1]["body"]["filter"]["email_addresses"]["email_address"]["$eq"] == "dana@x.com"


def test_update_normalizes_by_type_and_refuses_non_fv(env):
    plugin, client, calls = env
    out = json.loads(plugin.h_update_record({"object": "people", "record_id": "rec-1", "values": {
        "fv_partner_status": "Certified", "fv_vertical": "Dental", "fv_mtd_commission": "12.5",
        "fv_channel_lead": "kirk-1", "fv_active_practices": 3, "fv_next_action": "Call", "fv_next_action_due": "2026-11-20"}}))
    assert out["success"], out
    sent = [c for c in calls if c["method"] == "PATCH"][-1]["body"]["data"]["values"]
    assert sent["fv_partner_status"] == [{"status": "Certified"}]
    assert sent["fv_vertical"] == [{"option": "Dental"}]
    assert sent["fv_mtd_commission"] == [{"currency_value": 12.5}]
    assert sent["fv_channel_lead"] == [{"target_object": "people", "target_record_id": "kirk-1"}]
    assert sent["fv_active_practices"] == [{"value": 3.0}]
    assert sent["fv_next_action_due"] == [{"value": "2026-11-20"}]
    bad = json.loads(plugin.h_update_record({"object": "people", "record_id": "rec-1", "values": {"name": "X"}}))
    assert not bad["success"] and "fv_" in bad["error"]
    bad2 = json.loads(plugin.h_update_record({"object": "deals", "record_id": "rec-1", "values": {"fv_x": 1}}))
    assert not bad2["success"]


def test_notes_and_tasks(env):
    plugin, client, calls = env
    n = json.loads(plugin.h_add_note({"object": "companies", "record_id": "c-1", "title": "Call", "content": "Talked."}))
    assert n["success"] and n["note_id"] == "n1"
    assert calls[-1]["body"]["data"]["parent_object"] == "companies"
    t = json.loads(plugin.h_create_task({"content": "Follow up", "deadline": "2026-11-21T14:00:00Z",
                                         "object": "people", "record_id": "rec-1"}))
    assert t["success"] and t["task_id"] == "t1"
    assert calls[-1]["body"]["data"]["linked_records"] == [{"target_object": "people", "target_record_id": "rec-1"}]
    lst = json.loads(plugin.h_my_tasks({}))
    assert lst["success"] and lst["tasks"][0]["content"] == "Reach out"
    assert "is_completed=false" in calls[-1]["url"]
    done = json.loads(plugin.h_complete_task({"task_id": "t1"}))
    assert done["success"] and calls[-1]["body"] == {"data": {"is_completed": True}}


def test_no_delete_tool_registered(env):
    plugin, client, calls = env
    names = [t[0] for t in plugin.TOOLS]
    assert not any("delete" in n for n in names)
    assert not any(c["method"] == "DELETE" for c in calls)
