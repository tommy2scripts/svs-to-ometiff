# svs-to-ometiff Context

## Domain glossary

### Aperio SVS source
A tiled whole-slide image file from Aperio scanners. This project supports the subset using TIFF compression code 33007.

### Compression 33007
An Aperio-specific TIFF compression tag observed for raw YUYV YCbCr 4:2:2 tile payloads.

### Source metadata
TIFF and Aperio ImageDescription information needed before conversion, including dimensions, tile geometry, compression, MPP, and magnification.

### Tile decoding
Reading raw tile bytes from the SVS source and decoding YUYV payloads into RGB arrays.

### Level 0 staging
Writing decoded full-resolution RGB data to a disk-backed array before pyramid construction.

### Pyramid construction
Generating lower-resolution RGB image levels from level 0.

### OME BigTIFF output
The converted pyramidal OME-TIFF file written with BigTIFF support.

### SubIFD-linked pyramid
A TIFF pyramid where lower-resolution levels are linked as SubIFDs under the full-resolution image.

### Output verification
Post-conversion checks that confirm expected OME-TIFF structure, BigTIFF status, RGB levels, tile size, and physical pixel metadata.

### Structured progress event
A machine-readable progress update emitted by conversion code. It contains display text plus optional fields such as phase, percent, current, and total. Human-readable text is for display only; control flow should use structured fields.

### Batch plan
The planned mapping from input SVS paths to output OME-TIFF paths.

### Batch item
One source SVS path and its planned OME BigTIFF output path inside a batch plan.

### Output collision
A batch planning error where two or more inputs would write to the same output path.

### Conversion configuration
The normalized set of options required to run a conversion, represented by `ConvertConfig` in the core package.

### GUI conversion job
A GUI-owned job record that tracks request identity, persistence, worker execution, and event streaming. It should not duplicate conversion semantics unless that duplication adds real leverage.
