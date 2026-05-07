# 06 · monorepo

Two subprojects, namespaced with `@group`. Cross-group targets collect
tasks from both.

## Layout

```
.
├── tasks.py
├── api/
│   ├── src/
│   └── tests/
└── web/
    ├── src/
    └── tests/
```

## Run

```bash
ntask --list              # api.lint, api.test, web.lint, web.test, check, check_api_only
ntask -j 4 check          # all four subproject checks in parallel
ntask api.test            # target a single namespaced task
ntask check_api_only      # only api.*, not web.*
ntask --graph check       # print the DAG as text
```

## What to notice

- `@group("api")` applied to a class prefixes every `@task` method inside
  it with `api.` - so `Api.test` has fully qualified name `api.test`.
- Cross-group dependencies use `@task(deps=[Api.lint, Api.test, ...])`.
  Passing the class attribute resolves through the function's
  `__ntask_task__` marker to its real fqn (`api.lint`). String fqns
  (`deps=["api.lint"]`) work too. The body-level `depends()` form is for
  same-file bare-name references; it doesn't resolve dotted attributes
  or string fqns at graph-build time.
- Each subproject's `@cached(inputs=...)` uses a glob scoped to its own
  directory. Editing `web/` doesn't invalidate `api.*` tasks.
- There's no special "subproject" concept - `@group` is just a naming
  convention that keeps a flat task registry tidy.
- Want per-subproject aggregate targets? Define them outside the group
  class (`check_api_only` above) or in a separate group.
