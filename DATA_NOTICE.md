# Data Notice

This repository is intended to contain reverse-engineering notes, tools, SDK
experiments, and source examples only.

Do not publish original BBK firmware, dictionary databases, application BDAs,
DLX resources, audio files, bundled toolchains, or other copyrighted device
dump contents unless you have the rights to redistribute them.

The local workspace used during research may contain these directories:

```text
系统/
应用/
build/
```

They are ignored by `.gitignore`. Scripts and notes may refer to paths under
those directories, but users should provide their own local dump.

The setup script can download a public MIPS little-endian toolchain archive
under `tools/` so the SDK can build native BDA files locally. Do not commit the
downloaded archive or the extracted toolchain directory; both are generated
local state.
