# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions use the `v1`, `v1.x.y`
moving-tag scheme described in the README.

## [Unreleased]

## [1.0.0]

### Added

- Composite GitHub Action that packages a Kingdom Come: Deliverance (KCD1/KCD2) loose-file mod
  into game-ready `.pak` files and a release `.zip`.
- Portable pure-Python tool (`scripts/pak_kcd_mod.py` orchestrator and `scripts/zip_pak.py`
  packer) that produces CryPak-safe paks (no modification-time extra fields); runs on Windows,
  macOS, and Linux with only Python 3.8+ (no shell required).
- `deflate` (default) and `store` compression modes via the `compress` input / `PAK_COMPRESS`.
- Self-test CI workflow and a copy-paste consumer release workflow.
