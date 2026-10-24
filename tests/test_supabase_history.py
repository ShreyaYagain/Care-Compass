"""Supabase chat-history tests (via the SQLite fallback)."""
import unittest

from app.db import store
from app.api.history import list_history, get_history, delete_history
from app.schemas import TriageRequest, Location
from app.api.triage import triage_endpoint


class TestSupabaseHistory(unittest.TestCase):

    def _seed_session(self, user_id: str):
        created = store.create_session(user_id, language="en", input_mode="text", first_message="hello")
        return created["id"]

    def test_history_returns_5_newest_of_6(self):
        ids = [self._seed_session("user-1") for _ in range(6)]
        result = list_history(limit=5, user="user-1")
        self.assertEqual(len(result), 5)
        returned = {s.id for s in result}
        self.assertNotIn(ids[0], returned, "Oldest session should be dropped by limit=5")

    def test_history_detail_returns_steps_in_order(self):
        sid = self._seed_session("user-1")
        store.append_step(sid, 0, "user_message", {"text": "hello"})
        store.append_step(sid, 1, "follow_up_question", {"question": "Since when?"})
        store.append_step(sid, 2, "user_answer", {"text": "2 days"})
        store.append_step(sid, 3, "result", {"care_type": "paramedic_home_visit", "urgency": "same_day"})

        detail = get_history(sid, user="user-1")
        self.assertEqual(detail.id, sid)
        self.assertEqual([s.step_index for s in detail.steps], [0, 1, 2, 3])
        self.assertEqual([s.kind for s in detail.steps], ["user_message", "follow_up_question", "user_answer", "result"])

    def test_history_detail_other_user_404(self):
        sid = self._seed_session("user-1")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            get_history(sid, user="user-2")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_session(self):
        sid = self._seed_session("user-1")
        delete_history(sid, user="user-1")
        self.assertIsNone(store.get_session(sid, "user-1"))

    def test_triage_logs_history_and_returns_session_id(self):
        req = TriageRequest(
            user_input="papa ko do din se bukhar hai aur khansi bhi",
            language="hinglish",
            location=Location(lat=28.54, lng=77.27),
            conversation_history=[],
        )
        import asyncio
        resp = asyncio.run(triage_endpoint(request=req, debug=False, db=None, user="user-1"))
        self.assertIsNotNone(resp.session_id)
        session = store.get_session(resp.session_id, "user-1")
        self.assertIsNotNone(session)
        self.assertEqual(session["care_type"], "paramedic_home_visit")
        kinds = [s["kind"] for s in session["steps"]]
        self.assertIn("user_message", kinds)
        self.assertIn("result", kinds)

    def test_pii_masked_in_history(self):
        sid = self._seed_session("user-1")
        store.append_step(sid, 0, "user_message", {"text": "call me 9876543210 or x@y.com"})
        detail = get_history(sid, user="user-1")
        payload_text = detail.steps[0].payload.get("text", "")
        self.assertNotIn("9876543210", payload_text)
        self.assertNotIn("x@y.com", payload_text)

    def test_triage_then_history_endpoint_returns_session(self):
        """End-to-end: POST /triage, then GET /history returns that session."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        post = client.post(
            "/triage",
            json={"user_input": "papa ko bukhar hai", "language": "hinglish"},
            headers={"X-Device-Id": "test-device-1"},
        )
        self.assertEqual(post.status_code, 200)
        session_id = post.json().get("session_id")
        self.assertIsNotNone(session_id)

        hist = client.get("/history?limit=5", headers={"X-Device-Id": "test-device-1"})
        self.assertEqual(hist.status_code, 200)
        ids = [s["id"] for s in hist.json()]
        self.assertIn(session_id, ids, "session created by /triage must appear in /history")

        detail = client.get(f"/history/{session_id}", headers={"X-Device-Id": "test-device-1"})
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["id"], session_id)
        self.assertTrue(body["steps"], "history detail must contain steps")

    def test_history_is_per_device(self):
        """The history key is the device id header: devices do not share history."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        client.post(
            "/triage",
            json={"user_input": "device A only", "language": "en"},
            headers={"X-Device-Id": "device-a"},
        )
        a = client.get("/history?limit=5", headers={"X-Device-Id": "device-a"}).json()
        b = client.get("/history?limit=5", headers={"X-Device-Id": "device-b"}).json()
        a_ids = {s["id"] for s in a}
        b_ids = {s["id"] for s in b}
        self.assertTrue(a_ids)
        self.assertTrue(a_ids.isdisjoint(b_ids), "device A and device B must not share sessions")


if __name__ == "__main__":
    unittest.main()
