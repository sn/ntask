import unittest

from src import render


class WebTests(unittest.TestCase):
    def test_render(self):
        self.assertEqual(render("hello"), "<h1>hello</h1>")
