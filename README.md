# clap-to-fish

Generates fish shell completion files, given a command-line tool created with the Rust
clap library.
Recursively explores the --help command and subcommands and parses options as described.

Usage:
```bash
./make.py > ~/.config/fish/completions/git-branchless.fish && complete -c git-branchless -e && source ~/.config/fish/completions/git-branchless.fish
```

This was made to provide completions for the git-branchless tool.
The git-branchless subfolder contains the parsed --help data structure,
and a pre-generated copy of its completions.
