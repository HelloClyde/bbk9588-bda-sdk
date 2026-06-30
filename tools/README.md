# Toolchain

This directory is the local install/cache location for the MIPS little-endian
compiler toolchain used by the BDA SDK.

Default archive:

```text
g++-mipsel-none-elf-15.2.0.zip
```

Download and unpack it with:

```powershell
.\scripts\setup_toolchain.ps1
```

The build scripts automatically search:

```text
tools/g++-mipsel-none-elf-*/bin/mipsel-none-elf-gcc.exe
tools/g++-mipsel-none-elf-*/bin/mipsel-none-elf-objcopy.exe
```

The default download URL is:

```text
https://static.grumpycoder.net/pixel/mips/g++-mipsel-none-elf-15.2.0.zip
```

Only this README should be committed. The downloaded archive and extracted
directory are ignored because they are large generated local state.
