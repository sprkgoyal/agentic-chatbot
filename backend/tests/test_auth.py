import os
import unittest
from fastapi.testclient import TestClient

from app import app
from services import db_manager

class TestAuthAndRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_db_file = db_manager.DB_FILE
        db_manager.DB_FILE = os.path.join(db_manager.DB_DIR, "chatbot_test_auth.db")
        db_manager.init_db()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        db_manager.DB_FILE = cls.orig_db_file
        test_db = os.path.join(db_manager.DB_DIR, "chatbot_test_auth.db")
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    def setUp(self):
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions;")
        cursor.execute("DELETE FROM users;")
        conn.commit()
        conn.close()

    def test_auto_register_and_login(self):
        # Test auto registration on first login
        payload = {"username": "new_customer", "role": "customer", "name": "New Customer"}
        res = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("token", data)
        self.assertEqual(data["user"]["username"], "new_customer")
        self.assertEqual(data["user"]["role"], "customer")
        self.assertEqual(data["user"]["name"], "New Customer")

        # Test subsequent login gets the same user
        token1 = data["token"]
        payload2 = {"username": "new_customer"}
        res2 = self.client.post("/api/auth/login", json=payload2)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["user"]["id"], data["user"]["id"])
        self.assertNotEqual(data2["token"], token1) # New session token generated

    def test_profile_retrieval_and_update(self):
        # Login
        login_res = self.client.post("/api/auth/login", json={"username": "profile_user", "role": "customer"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Me endpoint
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["username"], "profile_user")

        # Update profile settings
        update_res = self.client.put(
            "/api/user/settings", 
            json={"name": "Updated Profile Name", "userpic": "avatar_cool_cat"},
            headers=headers
        )
        self.assertEqual(update_res.status_code, 200)

        # Re-check Me
        me_res2 = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res2.json()["name"], "Updated Profile Name")
        self.assertEqual(me_res2.json()["userpic"], "avatar_cool_cat")

    def test_role_based_access_control(self):
        # Create a Customer session
        customer_login = self.client.post("/api/auth/login", json={"username": "cust_user", "role": "customer"})
        customer_token = customer_login.json()["token"]
        cust_headers = {"Authorization": f"Bearer {customer_token}"}

        # Create an Admin session
        admin_login = self.client.post("/api/auth/login", json={"username": "adm_user", "role": "admin"})
        admin_token = admin_login.json()["token"]
        adm_headers = {"Authorization": f"Bearer {admin_token}"}

        # Admin sync endpoint: customer should be blocked (403), admin should be allowed (returns 200 or logs progress)
        res_sync_cust = self.client.post("/api/sync/confluence", json={"space_id": "TEST"}, headers=cust_headers)
        self.assertEqual(res_sync_cust.status_code, 403)

        # Chat endpoint: admin should be blocked (403), customer should be allowed (starts stream, but missing API keys will be 400 or 404 conversation)
        # Note: missing conversation is 404 for customer
        res_chat_adm = self.client.post("/api/chat", json={"message": "hello", "conversation_id": "none"}, headers=adm_headers)
        self.assertEqual(res_chat_adm.status_code, 403)

    def test_delete_account(self):
        login_res = self.client.post("/api/auth/login", json={"username": "delete_me", "role": "customer"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        del_res = self.client.delete("/api/auth/delete-account", headers=headers)
        self.assertEqual(del_res.status_code, 200)

        # Session should be invalid now
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 401)

if __name__ == "__main__":
    unittest.main()
