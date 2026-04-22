from textwrap import dedent


def build_tui() -> str:
    return dedent(
        """\
        ┌─────────────────────────── Milknado ───────────────────────────┐
        │ backend   │ python                                             │
        │ frontend  │ typescript commander                               │
        │ status    │ curds spinning and terminal ready                  │
        │ next step │ run `npx cheese-flow milknado` anytime you want it │
        └─────────────────────────────────────────────────────────────────┘
        """
    )


if __name__ == "__main__":
    print(build_tui())
