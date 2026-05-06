# Validation Protocol

## Scope

Use this protocol to validate `svs-to-ometiff` outputs before relying on a converted slide in downstream spatial workflows. The current goal is lean local validation, not a broad CI matrix.

## 1. Structural checks

Run after each conversion:

```bash
python - <<'PY'
import tifffile
path = "output.ome.tiff"
with tifffile.TiffFile(path) as tif:
    assert tif.is_ome, "missing OME metadata"
    assert tif.is_bigtiff, "expected BigTIFF"
    levels = tif.series[0].levels
    assert len(levels) >= 1, "missing image levels"
    assert levels[0].shape[-1] == 3, "expected RGB"
    print([level.shape for level in levels])
PY
```

Pass: OME metadata parses, BigTIFF opens, expected level count and RGB shapes are present.

## 2. Pixel round-trip checks

For synthetic fixtures, run:

```bash
python -m pytest tests/test_integration.py tests/test_streaming_writer.py -v
```

Pass: level 0 equals expected RGB pixels and downsampled levels equal expected block averages.

## 3. Memory profiling

Run:

```bash
python -m pytest tests/test_memory.py -v -s
```

| Case | Target |
| --- | --- |
| Small synthetic RGB | profile is reproducible |
| Medium synthetic RGB | peak trends below old full-pyramid path |
| Strict local mode | `SVS_OMETIFF_STRICT_MEMORY=1` enforces `<1.2 x H x W x 3` |

Memory numbers vary with OS page cache and TIFF buffers, so strict mode is local/manual until stable.

## 4. Real SVS validation

For each real file, record:

- source path or anonymized ID
- scanner/model/firmware if known
- source Compression tag (`33007` required)
- dimensions and tile size
- conversion command
- output level shapes
- visual thumbnail review result
- downstream import result if tested

## 5. Current real-file record

| Field | Result |
| --- | --- |
| Source | `67174_PT_Lung.svs` |
| Compression | `33007` |
| Dimensions / tile | `39599 x 39858`, source `256 x 256`, output `512 x 512` |
| Command | `--num-levels 3 --compression none --tile-size 512` |
| Output levels | `(39858, 39599, 3)`, `(19929, 19799, 3)`, `(9964, 9899, 3)` |
| Structural result | BigTIFF + OME metadata + 2 SubIFDs present |
| Visual review | Pending manual thumbnail review |

Note: LZW retry failed in the local Python 3.9 environment because `imagecodecs` was unavailable; uncompressed output completed successfully.

## Pass/fail criteria

Pass only if structural checks pass, synthetic pixel tests pass, no conversion exceptions occur, and visual review shows no obvious channel/order/tile artifacts.

Fail if OME metadata is missing, pyramid levels are absent/unexpected, pixel tests fail, output cannot reopen with tifffile, or visual review shows corruption.

## Current limits

Do not add full CI validation for real SVS files until 3+ real compression-33007 SVS files from distinct contexts have been tested and documented.
