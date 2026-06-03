import os
import unittest
from unittest.mock import patch, MagicMock
from tools import confluence_tools
from services.vector_service import VectorService

class TestConfluenceCQLSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_url = confluence_tools.CONFLUENCE_URL
        cls.orig_token = confluence_tools.CONFLUENCE_API_TOKEN
        cls.orig_user = confluence_tools.CONFLUENCE_USERNAME

    @classmethod
    def tearDownClass(cls):
        confluence_tools.CONFLUENCE_URL = cls.orig_url
        confluence_tools.CONFLUENCE_API_TOKEN = cls.orig_token
        confluence_tools.CONFLUENCE_USERNAME = cls.orig_user

    @patch('tools.confluence_tools.requests.get')
    def test_fetch_confluence_pages_by_space_success(self, mock_get):
        # Configure dummy credentials
        confluence_tools.CONFLUENCE_URL = "https://mock-confluence.net/wiki"
        confluence_tools.CONFLUENCE_API_TOKEN = "mock_token"
        confluence_tools.CONFLUENCE_USERNAME = "mock_user"

        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "1001",
                    "title": "Architecture Specification",
                    "body": {"storage": {"value": "<p>System specification</p>"}},
                    "version": {"when": "2026-05-15T12:00:00Z"},
                    "ancestors": []
                }
            ]
        }
        mock_get.return_value = mock_response

        # Execute
        pages = confluence_tools.fetch_confluence_pages_by_space("ENG")
        
        # Verify
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["id"], "1001")
        self.assertEqual(pages[0]["space_id"], "ENG")
        self.assertEqual(pages[0]["title"], "Architecture Specification")
        self.assertEqual(pages[0]["body"], "<p>System specification</p>")
        
        # Verify URL called
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://mock-confluence.net/wiki/rest/api/content/search")
        self.assertEqual(kwargs["params"]["cql"], "space = 'ENG' AND type = 'page'")

    @patch('tools.confluence_tools.requests.get')
    def test_fetch_confluence_pages_fallback_mock(self, mock_get):
        # If API configuration is missing, should fall back to mock pages
        confluence_tools.CONFLUENCE_URL = None
        confluence_tools.CONFLUENCE_API_TOKEN = None
        confluence_tools.CONFLUENCE_USERNAME = None

        pages = confluence_tools.fetch_confluence_pages_by_space("TEST_SPACE")
        self.assertGreater(len(pages), 0)
        self.assertEqual(pages[0]["space_id"], "TEST_SPACE")
        self.assertEqual(pages[0]["title"], "Engineering Architecture Hub") # From mock data

if __name__ == "__main__":
    unittest.main()
