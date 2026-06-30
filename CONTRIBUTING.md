# Contributing

This project mixes hardware-tested facts, static reverse engineering, and
experimental probes. Please label claims clearly:

- `confirmed`: observed on real hardware
- `static`: inferred from disassembly or binary structure
- `probe`: a generated test app exists, but behavior may still be incomplete
- `guess`: do not use this for SDK names or public API claims

When adding SDK wrappers:

1. Keep uncertain names suffixed with `_LIKE`.
2. Link the note or report that supports the offset.
3. Mention the probe BDA and observed hardware result when available.
4. Avoid committing original firmware, application binaries, DLX resources,
   generated BDA files, or local toolchains.

Generated analysis files belong in `build/` or should stay ignored unless they
are curated into a small Markdown report.
