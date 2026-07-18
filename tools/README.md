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
tools/bin/mipsel-none-elf-gcc.exe
tools/bin/mipsel-none-elf-objcopy.exe
tools/g++-mipsel-none-elf-*/bin/mipsel-none-elf-gcc.exe
tools/g++-mipsel-none-elf-*/bin/mipsel-none-elf-objcopy.exe
```

The default download URL is:

```text
https://static.grumpycoder.net/pixel/mips/g++-mipsel-none-elf-15.2.0.zip
```

Expected SHA-256:

```text
8BA866E25C9826EE04AB4310365D264E3E73769E3738BB58AE38FD6740B7EE8D
```

`setup_toolchain.ps1` rejects the archive before extraction if this hash does
not match.

Only this README should be committed. The downloaded archive and extracted
directory are ignored because they are large generated local state.
