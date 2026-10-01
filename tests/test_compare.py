
import json
import os
import threading
import unittest
import urllib.request
from unittest import mock

import app


class CompareTests(unittest.TestCase):
    def offers(self):
        return [
            {"position": 1, "title": "XM5", "source": "Imagine", "extracted_price": 24990, "price": "₹24,990", "tag": "Out of stock"},
            {"position": 2, "title": "XM5", "source": "Cashify", "extracted_price": 18499, "price": "₹18,499", "second_hand_condition": "refurbished"},
            {"position": 3, "title": "XM5", "source": "Flipkart", "extracted_price": 26490, "price": "₹26,490", "delivery": "Free delivery"},
            {"position": 4, "title": "XM5", "source": "Amazon.in", "extracted_price": 26990, "price": "₹26,990"},
            {"position": 5, "title": "XM5", "source": "Amazon.in", "extracted_price": 27100, "price": "₹27,100"},
            {"position": 6, "title": "XM5 USD", "source": "Import Shop", "extracted_price": 199, "price": "$199.00"},
            {"position": 7, "title": "XM5", "source": "Mystery", "snippet": "Call for price"},
        ]

    def test_cheapest_in_stock_skips_oos_and_used(self):
        result = app.compare_offers(self.offers(), include_used=False)
        self.assertEqual(result["cheapest"]["retailer"], "Flipkart")
        self.assertEqual(result["cheapest"]["price"], 26490)
        names = [row["retailer"] for row in result["retailers"]]
        self.assertEqual(names, ["Flipkart", "Amazon.in"])
        self.assertEqual(result["gap_to_next"]["versus"], "Amazon.in")
        self.assertEqual(result["gap_to_next"]["amount"], 500)
        excluded = {row["retailer"] for row in result["excluded"]}
        self.assertIn("Imagine", excluded)
        self.assertIn("Cashify", excluded)
        self.assertIn("Import Shop", excluded)
        self.assertIn("Mystery", excluded)

    def test_include_used_lets_refurbished_win(self):
        result = app.compare_offers(self.offers(), include_used=True)
        self.assertEqual(result["cheapest"]["retailer"], "Cashify")

    def test_inr_grouping(self):
        self.assertEqual(app.format_inr(26490), "₹26,490")
        self.assertEqual(app.format_inr(1299990), "₹12,99,990")

    def test_sample_is_labeled_and_not_live(self):
        os.environ.pop("SERPAPI_KEY", None)
        payload = app.build_response("Sony WH-1000XM5", "Bengaluru, Karnataka, India", False, False)
        self.assertTrue(payload["sample"])
        self.assertIn("not live", payload["disclaimer"].lower())
        self.assertEqual(payload["cheapest"]["retailer"], "Flipkart")
        self.assertEqual(payload["engine"], "google_shopping")

    def test_redacts_key(self):
        os.environ["SERPAPI_KEY"] = "super-secret-key"
        try:
            text = app.redact("Invalid API key super-secret-key in https://serpapi.com/search.json?api_key=super-secret-key&q=x")
        finally:
            os.environ.pop("SERPAPI_KEY", None)
        self.assertNotIn("super-secret-key", text)
        self.assertIn("[redacted]", text)


class ServerTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("SERPAPI_KEY", None)
        self.httpd = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_status_and_search_without_key(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/status") as response:
            status = json.loads(response.read().decode())
        self.assertFalse(status["has_key"])
        self.assertEqual(status["mode"], "sample")
        body = json.dumps({"query": "boAt Airdopes 141", "sample": False}).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/search",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode())
        self.assertTrue(payload["sample"])
        self.assertTrue(payload["cheapest"]["in_stock"])
        page = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/").read().decode()
        self.assertIn("Price Gap", page)

    def test_live_key_is_not_returned_and_sample_skips_network(self):
        os.environ["SERPAPI_KEY"] = "live-key-should-not-leak"
        try:
            with mock.patch.object(app.urllib.request, "urlopen", side_effect=AssertionError("called")):
                payload = app.build_response("XM5", "Bengaluru, Karnataka, India", False, True)
            self.assertTrue(payload["sample"])
            self.assertNotIn("live-key-should-not-leak", json.dumps(payload))
        finally:
            os.environ.pop("SERPAPI_KEY", None)


if __name__ == "__main__":
    unittest.main()
