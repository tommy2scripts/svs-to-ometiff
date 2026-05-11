# Real File Validation Record

Use this template to collect validation evidence for real Aperio SVS files.
Do not commit actual SVS or OME-TIFF files to the repository — record only
metadata and observations.

## Source

- Anonymized ID:
- Scanner model (e.g. Aperio AT2, GT450):
- Firmware/export settings, if known:
- Tissue/stain:
- Source dimensions (W x H):
- Source tile size:
- Compression tag (should be 33007):
- MPP:

## Command

```bash
svs-to-ometiff input.svs output.ome.tiff --compression none --num-levels 3 --tile-size 512
```

## Structural Output

Run `svs-to-ometiff-verify output.ome.tiff --min-levels 3` and record:

- `is_ome`:
- `is_bigtiff`:
- Level shapes:
- SubIFD count:
- Output file size:
- Peak RSS (from `time` or memory test):

## Visual Review

Generate a thumbnail for visual inspection:

```bash
python3 -c "
import tifffile
from PIL import Image
with tifffile.TiffFile('output.ome.tiff') as tif:
    level = tif.series[0].levels[-1].asarray()
Image.fromarray(level).save('output_thumbnail.png')
"
```

- [ ] Thumbnail generated successfully
- [ ] No obvious channel swap
- [ ] No tiled seams
- [ ] No major color artifacts
- Reviewer/date:

## Downstream Import

Test the OME-TIFF in downstream tools (QuPath, Bio-Formats, napari, etc.):

- Tool:
- Version:
- Result (opens correctly / errors):
- Notes:
