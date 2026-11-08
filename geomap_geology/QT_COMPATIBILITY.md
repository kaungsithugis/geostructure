# GeoStructure 0.12.1 — compatibility maintenance

Based on the published GeoStructure 0.12.0 installer, not the held 0.13.0 draft.
Author: Kaung Si Thu.

## Corrections

All 61 enum locations reported in the provided QGIS repository checker output
were replaced with their scoped spellings:

| File | Enum locations corrected |
|---|---:|
| csv_import.py | 9 |
| cross_section.py | 17 |
| strike_rose.py | 5 |
| plugin.py | 11 |
| stereoplot.py | 19 |
| Total | 61 |

Examples:
- QDialogButtonBox.Ok -> QDialogButtonBox.StandardButton.Ok
- QMessageBox.Yes -> QMessageBox.StandardButton.Yes
- Qt.LeftButton -> Qt.MouseButton.LeftButton
- Qt.AlignCenter -> Qt.AlignmentFlag.AlignCenter
- QPainter.Antialiasing -> QPainter.RenderHint.Antialiasing
- QImage.Format_RGB32 -> QImage.Format.Format_RGB32
- QgsMapLayerProxyModel.PointLayer -> QgsMapLayerProxyModel.Filter.PointLayer
- QgsWkbTypes.PointGeometry -> QgsWkbTypes.GeometryType.PointGeometry
- QgsVectorFileWriter.NoError -> QgsVectorFileWriter.WriterError.NoError

Cross Section now obtains event x coordinates using position() on modern Qt
and pos() as a fallback for older Qt5 events. The Flake8 E731 assigned lambda
was replaced by a local def with the same predicate.

No new analysis tools were added. Geological calculations, symbols, colors,
CSV conventions and saved-data formats were retained.

## Verification completed

Actual runtime: QGIS 3.40.6 / Qt5, Linux, offscreen.
- Every distinct changed enum resolves and equals its old Qt5 value.
- All four tool dialogs construct and plugin menu actions load/unload.
- Measurement CSV import and GeoPackage output.
- Schmidt/Wulff stereonet PNG/SVG exports, strike rose PNG/SVG.
- Cross-section PNG/SVG, labels, zoom/reset, A/A-prime map markers.
- Modern position() / older pos() event branches exercised with test objects.
- Static scan confirms none of the 61 old enum spellings remain.

## Limits and metadata

A real Qt6/QGIS4 installation was NOT available here. Passing these tests does
not certify full Qt6 or QGIS4 runtime compatibility. The official repository
scanner has not been rerun on this ZIP yet.

metadata.txt retains qgisMinimumVersion=3.28 and qgisMaximumVersion=3.99.
Do not change the maximum to 4.99 until the complete plugin has been tested
with QGIS4/Qt6. Do not add supportsQt6=True: that flag is obsolete.

This ZIP is a local review/test candidate; no GitHub or QGIS upload was made.
When ready, update the public repository source and upload this exact version
as a new plugin version. Check the new version's Qt6 Check and Security tabs;
older version scan results will still describe the older source.

Official guidance: https://plugins.qgis.org/docs/migrate-qgis4
