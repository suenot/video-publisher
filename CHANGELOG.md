# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic
Versioning.

## [Unreleased]

## [0.1.3] - 2026-08-11

### Fixed

- Wait for the Studio video editor to mount before changing visibility.
- Preserve Studio's selected timed-caption option before continuing.

## [0.1.2] - 2026-08-11

### Fixed

- Upload timed caption files through Studio's current `Upload manual` dialog.

## [0.1.1] - 2026-08-11

### Fixed

- Open the target channel's upload route directly instead of returning through
  the Studio dashboard.
- Stop after one bounded upload-dialog attempt when Studio does not mount a
  file input.

## [0.1.0] - 2026-08-11

### Fixed

- Wait for the active YouTube Studio channel before using channel controls.
- Wait for the upload launcher to become visible before starting an upload.
