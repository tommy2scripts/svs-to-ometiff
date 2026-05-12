# Security Policy

## Scope

This tool processes Aperio SVS files which are TIFF-format images. While a maliciously crafted TIFF could exploit vulnerabilities in image parsing libraries (`tifffile`, `numpy`, `imagecodecs`), the tool does not execute code from the input file, make network requests during conversion, or install system packages without user consent.

## Reporting a vulnerability

If you discover a security issue in svs-to-ometiff, please do not open a public issue. Report it by emailing ttran@biochain.com.

We will acknowledge receipt within 48 hours and provide an assessment within 5 business days.

## Dependencies

Security updates for dependencies (`tifffile`, `numpy`, `imagecodecs`) are applied via the standard pip update workflow. Always install from PyPI or trusted sources.
