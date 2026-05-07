from ntask import cached, task


@task
@cached(inputs=["greeting.txt"])
def hello():
    """Greet whoever's named in greeting.txt."""
    name = open("greeting.txt").read().strip()
    print(f"Hello, {name}!")
