import os
import unittest
from services import db_manager

class TestDatabaseManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Override the database file path for testing isolation
        cls.orig_db_file = db_manager.DB_FILE
        db_manager.DB_FILE = os.path.join(db_manager.DB_DIR, "chatbot_test.db")
        db_manager.init_db()

    @classmethod
    def tearDownClass(cls):
        db_manager.DB_FILE = cls.orig_db_file
        test_db = os.path.join(db_manager.DB_DIR, "chatbot_test.db")
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    def setUp(self):
        # Clean tables
        conn = db_manager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages;")
        cursor.execute("DELETE FROM conversations;")
        cursor.execute("DELETE FROM sessions;")
        cursor.execute("DELETE FROM users;")
        conn.commit()
        conn.close()

    def test_user_creation_and_fetching(self):
        user = db_manager.create_user("john_doe", "hashed_pass", "customer", "John Doe", "avatar_green_frog")
        self.assertEqual(user["username"], "john_doe")
        self.assertEqual(user["role"], "customer")
        self.assertEqual(user["name"], "John Doe")
        self.assertEqual(user["userpic"], "avatar_green_frog")
        
        fetched = db_manager.get_user_by_id(user["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["username"], "john_doe")
        
        fetched_by_name = db_manager.get_user_by_username("john_doe")
        self.assertIsNotNone(fetched_by_name)
        self.assertEqual(fetched_by_name["id"], user["id"])
        
        # Test integrity constraints (duplicate usernames)
        with self.assertRaises(ValueError):
            db_manager.create_user("john_doe", "pass", "admin", "Another John", "avatar_1")

    def test_user_update_and_delete(self):
        user = db_manager.create_user("update_me", "pass", "customer", "Old Name", "avatar_1")
        
        success = db_manager.update_user_profile(user["id"], "New Name", "avatar_new")
        self.assertTrue(success)
        
        updated = db_manager.get_user_by_id(user["id"])
        self.assertEqual(updated["name"], "New Name")
        self.assertEqual(updated["userpic"], "avatar_new")
        
        # Delete user
        deleted = db_manager.delete_user_account(user["id"])
        self.assertTrue(deleted)
        self.assertIsNone(db_manager.get_user_by_id(user["id"]))

    def test_sessions(self):
        user = db_manager.create_user("session_user", "pass", "admin", "Session User", "avatar_2")
        token = db_manager.create_session(user["id"])
        self.assertIsNotNone(token)
        
        session_user = db_manager.get_user_by_token(token)
        self.assertIsNotNone(session_user)
        self.assertEqual(session_user["username"], "session_user")
        
        # Delete session
        logout_success = db_manager.delete_session(token)
        self.assertTrue(logout_success)
        self.assertIsNone(db_manager.get_user_by_token(token))

    def test_conversations_and_messages(self):
        user = db_manager.create_user("chat_user", "pass", "customer", "Chat User", "avatar_3")
        
        # Create conversation
        conv = db_manager.create_conversation(user["id"], "System Architecture Discussion")
        self.assertEqual(conv["title"], "System Architecture Discussion")
        
        # Verify lists
        convs = db_manager.list_conversations(user["id"])
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0]["id"], conv["id"])
        
        # Create messages
        msg1 = db_manager.create_message(conv["id"], "user", "How does User Service authenticate?")
        self.assertEqual(msg1["role"], "user")
        self.assertEqual(msg1["content"], "How does User Service authenticate?")
        
        msg2 = db_manager.create_message(conv["id"], "ai", "User Service uses JWT Bearer tokens.", is_error=False, status_logs=["Connecting to DB...", "Querying Chroma..."])
        self.assertEqual(msg2["role"], "ai")
        self.assertEqual(msg2["is_error"], False)
        self.assertEqual(msg2["status_logs"], ["Connecting to DB...", "Querying Chroma..."])
        
        # Fetch message history
        messages = db_manager.list_messages(conv["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["content"], "How does User Service authenticate?")
        self.assertEqual(messages[1]["status_logs"], ["Connecting to DB...", "Querying Chroma..."])
        
        # Delete conversation
        del_conv = db_manager.delete_conversation(conv["id"])
        self.assertTrue(del_conv)
        self.assertEqual(len(db_manager.list_conversations(user["id"])), 0)
        # Verify cascading deletion of messages
        self.assertEqual(len(db_manager.list_messages(conv["id"])), 0)

if __name__ == "__main__":
    unittest.main()
