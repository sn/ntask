"""Shell completion script generation.

Emits a stub for bash, zsh, or fish that calls back into ``ntask`` for the
list of tasks (and per-task flags). Task discovery is dynamic, so we
ship script bodies rather than pre-baked task lists.
"""
from __future__ import annotations

from typing import Literal

Shell = Literal["bash", "zsh", "fish"]


_BASH = r'''
# ntask bash completion. Source me from ~/.bashrc:
#   source <(ntask --completion bash)
_ntask_complete() {
    local cur prev words cword
    _get_comp_words_by_ref -n : cur prev words cword

    if [[ $cword -eq 1 ]]; then
        local tasks
        tasks="$(ntask --completion-tasks 2>/dev/null)"
        # Built-ins not listed by `--completion-tasks`.
        tasks+=" clean init watch"
        COMPREPLY=( $(compgen -W "$tasks" -- "$cur") )
        return 0
    fi
    if [[ "$cur" == --* ]]; then
        local flags
        flags="$(ntask --completion-flags "${words[1]}" 2>/dev/null)"
        COMPREPLY=( $(compgen -W "$flags" -- "$cur") )
        return 0
    fi
    COMPREPLY=()
}
complete -F _ntask_complete ntask
'''.lstrip()


_ZSH = r'''
#compdef ntask
# ntask zsh completion. Either drop this into a file on $fpath named `_ntask`,
# or eval it directly:
#   eval "$(ntask --completion zsh)"
_ntask() {
    local -a tasks flags
    if (( CURRENT == 2 )); then
        tasks=( ${(f)"$(ntask --completion-tasks 2>/dev/null)"} clean init watch )
        _describe 'task' tasks
        return
    fi
    if [[ "$words[CURRENT]" == --* ]]; then
        flags=( ${(f)"$(ntask --completion-flags "$words[2]" 2>/dev/null)"} )
        _describe 'flag' flags
    fi
}
_ntask "$@"
'''.lstrip()


_FISH = r'''
# ntask fish completion. Install with:
#   ntask --completion fish | source
#   ntask --completion fish > ~/.config/fish/completions/ntask.fish
function __ntask_tasks
    ntask --completion-tasks 2>/dev/null
    echo clean
    echo init
    echo watch
end

function __ntask_flags
    set -l cmd (commandline -opc)
    if test (count $cmd) -ge 2
        ntask --completion-flags $cmd[2] 2>/dev/null
    end
end

complete -c ntask -f -n 'not __fish_seen_subcommand_from (__ntask_tasks)' -a '(__ntask_tasks)'
complete -c ntask -f -n '__fish_seen_subcommand_from (__ntask_tasks)' -a '(__ntask_flags)'
'''.lstrip()


def completion_script(shell: Shell) -> str:
    if shell == "bash":
        return _BASH
    if shell == "zsh":
        return _ZSH
    if shell == "fish":
        return _FISH
    raise ValueError(f"unknown shell: {shell!r}")
