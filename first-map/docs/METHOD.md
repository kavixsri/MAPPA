# Method notes

**Analysis grid.** Everything is resampled once onto a metric grid in the ortho's CRS (default 1 m/px). Large orthomosaics are streamed by GDAL (`average` resampling), so a 5 cm ortho of ~1 km² does not need to fit in RAM.

**GCP-free georeferencing.** ODM places the ortho using camera GPS only. MAPPA matches SIFT features between the (blurred-to-base-resolution) ortho and the base image, fits a similarity transform with RANSAC (scale restricted to 0.9–1.1), and applies it **to the GeoTIFF's geotransform only** — pixels are never resampled, so the full-resolution ortho is preserved. Fallback: FFT phase correlation (translation only) with a conservative error bound.

**Error budget.** `acc95 = sqrt(base_acc95² + (2·registration_RMS)²)`. The base layer dominates; the number is an *assumption-driven bound*, printed with "unverified against ground truth".

**Colour change.** Per-channel quantile-matched linear radiometric normalisation (so season/lighting is not read as change) → both images blurred to the base resolution → RGB distance → threshold `max(median + 5·MAD, 22)` → open/close → minimum area 150 m².

**Height cue.** DSM (ODM) − DEM (Copernicus), with the vertical bias between them removed (median over unchanged ground; ODM without GCPs has metres of vertical offset). Used to *confirm* blocking. Trees and buildings also appear in DSM−DEM, so it is never used alone.

**Road scoring.** OSM lines → 20 m segments → 5 m flat-cap buffer → fraction of valid pixels changed and mean |height anomaly|.
BLOCKED: ≥ 40 % changed **and** ≥ 0.5 m height anomaly (without DSM: ≥ 60 % changed). UNCERTAIN: ≥ 15 % changed. Segments with < 50 % valid coverage are NO_DATA.

**Validation.** `mappa/demo_data.py` builds a synthetic scene with a known injected georeference error (offset + 0.3° rotation), a known slide footprint, a vertical DSM bias, and a coarse, differently-lit, differently-projected base image. This is the only place ground truth exists; it demonstrates the method, not field accuracy.
