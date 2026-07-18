# Changelog

All notable SDK and packer changes are recorded here. The project follows
[Semantic Versioning](https://semver.org/) once a public release is tagged.

## Unreleased

- Prepare the repository for an initial open-source SDK release.
- Add installable `bda-pack`, `bda-validate`, and `bda-icon` commands.
- Package verified public headers with the Python wheel.
- Add CI, compatibility documentation, and a focused developer quick start.
- License original project material under Apache License 2.0 and document
  third-party data boundaries in `NOTICE` and `DATA_NOTICE.md`.

## 0.1.0-alpha.1

- Build standalone MIPS little-endian BDA applications from freestanding C.
- Validate BDA headers, entry points, checksums, and VX icon regions.
- Publish dynamically verified filesystem, GUI, input, controls, dialogs,
  graphics, and raw PCM APIs.
- Include source and prebuilt binaries for verified examples.
