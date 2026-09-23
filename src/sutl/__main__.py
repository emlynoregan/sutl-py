"""Allow ``python -m sutl`` to run the CLI."""

from .cli import main

raise SystemExit(main())
