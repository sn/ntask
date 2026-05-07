import unittest


def greet(name: str) -> str:
    return f"hello, {name}"


class GreetTests(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet("world"), "hello, world")
