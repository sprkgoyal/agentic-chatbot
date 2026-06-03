import os
import unittest
from fastapi.testclient import TestClient

from app import app
from services import db_manager

class TestChatEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_db_file = db_manager.DB_FILE
        db_manager.DB_FILE = os.path.join(db_manager.DB_DIR, "chatbot_test_chat.db")
        db_manager.init_db()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        db_manager.DB_FILE = cls.orig_db_file
        test_db = os.path.join(db_manager.DB_DIR, "chatbot_test_chat.db")
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    def setUp(self):
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages;")
        cursor.execute("DELETE FROM conversations;")
        cursor.execute("DELETE FROM sessions;")
        cursor.execute("DELETE FROM users;")
        conn.commit()
        conn.close()

    def test_conversation_crud_and_download(self):
        # Login
        login_res = self.client.post("/api/auth/login", json={"username": "chat_user", "role": "customer"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a conversation
        create_res = self.client.post("/api/conversations", json={"title": "Test Chat"}, headers=headers)
        self.assertEqual(create_res.status_code, 200)
        conv_id = create_res.json()["id"]

        # 2. Add some mock messages directly through DB manager
        db_manager.create_message(conv_id, "user", "Hello Assistant")
        db_manager.create_message(conv_id, "ai", "Hello User! How can I help you?", is_error=False, status_logs=["log1"])

        # 3. Retrieve messages from endpoint
        msg_res = self.client.get(f"/api/conversations/{conv_id}/messages", headers=headers)
        self.assertEqual(msg_res.status_code, 200)
        messages = msg_res.json()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["content"], "Hello Assistant")
        self.assertEqual(messages[1]["status_logs"], ["log1"])

        # 4. Download chat as text
        dl_res = self.client.get(f"/api/conversations/{conv_id}/download", headers=headers)
        self.assertEqual(dl_res.status_code, 200)
        self.assertIn("Conversation Title: Test Chat", dl_res.text)
        self.assertIn("User: Hello Assistant", dl_res.text)
        self.assertIn("AI Assistant: Hello User! How can I help you?", dl_res.text)

        # 5. Delete conversation
        del_res = self.client.delete(f"/api/conversations/{conv_id}", headers=headers)
        self.assertEqual(del_res.status_code, 200)

        # 6. Verify deleted
        list_res = self.client.get("/api/conversations", headers=headers)
        self.assertEqual(len(list_res.json()), 0)

if __name__ == "__main__":
    unittest.main()
