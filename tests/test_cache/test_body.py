from ntask._cache.body import hash_task_body, hash_task_body_source


def test_body_hash_stable_for_same_function():
    def f():
        x = 1
        return x + 1

    assert hash_task_body(f) == hash_task_body(f)


def test_body_hash_changes_on_code_change():
    def f1():
        return 1

    def f2():
        return 2

    assert hash_task_body(f1) != hash_task_body(f2)


def test_body_hash_ignores_docstring():
    src_a = "def f():\n    \"\"\"old docstring\"\"\"\n    return 42\n"
    src_b = "def f():\n    \"\"\"completely different docstring\"\"\"\n    return 42\n"
    assert hash_task_body_source(src_a) == hash_task_body_source(src_b)


def test_body_hash_source_ignores_comments():
    src_a = "def f():\n    # comment A\n    return 1\n"
    src_b = "def f():\n    # comment B - totally different\n    return 1\n"
    assert hash_task_body_source(src_a) == hash_task_body_source(src_b)


def test_body_hash_source_ignores_whitespace_and_formatting():
    src_a = "def f():\n    return 1\n"
    src_b = "def f(  ):\n\n    return   1\n"
    assert hash_task_body_source(src_a) == hash_task_body_source(src_b)
