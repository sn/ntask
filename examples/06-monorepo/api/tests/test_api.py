import unittest

from src import endpoint


class ApiTests(unittest.TestCase):
    def test_endpoint(self):
        self.assertEqual(endpoint("world"), {"hello": "world"})
