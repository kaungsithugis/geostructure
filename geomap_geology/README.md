# GeoStructure

A QGIS 3 plugin for styling vector layers already loaded in your project.

1. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP**.
2. Select the ZIP as downloaded, install it, and enable the plugin if needed.
3. Load your geological layers in QGIS. Open **Plugins → GeoStructure → Geomap Visualizer**.
4. Choose a visualization, layer and attribute field. Click **Apply style**. Save your QGIS project to retain the result.

| Mode | Input | Example attributes |
| --- | --- | --- |
| Geological units | Polygon | Unit, formation or lithology name |
| Faults | Line | strike-slip, dextral, sinistral, reverse, thrust, normal |
| Bedding | Point | Strike 0–360°, optional dip 0–90° |

Fault colors are blue for strike-slip, red for reverse/thrust, green for normal and dashed gray for other values. The units palette repeats after 12 categories. Bedding strike is interpreted in clockwise right-hand-rule degrees, with the dip tick 90° clockwise from strike. Use a north-up map with strike values referenced to map/grid north. Convert true-north bearings if grid convergence is material to your map. A gray dot identifies missing or invalid strike. A dip label, if requested, appears where QGIS can place it.

The plugin replaces the selected layer's renderer. To keep an existing renderer, duplicate the layer in QGIS or save its style before applying the plugin. Source geometries and attributes are unchanged. Keep the plugin installed so the bedding SVG remains available when reopening the project.

## Plot strike and dip directly from CSV

Use **Plugins → GeoStructure → Structural Plot**. Choose a UTF-8,
comma-separated CSV with a header row, map latitude, longitude, dip, and either strike or dip direction, and select **Save
and plot**. Choose a new GeoPackage filename, then save your QGIS project to
retain the styling. Example measurements are synthetic.

Input coordinates must be WGS 84 decimal degrees. Dip is 0–90°. Strike and dip
direction are azimuths of 0–360°, clockwise from north. If you select a dip
direction column, it controls the plotted orientation, even if a strike column
is also selected. The plugin preserves the original strike and computes RHR
strike as (dip direction − 90°) modulo 360°. When no dip direction column is
selected, the selected strike must already follow RHR. The GeoPackage stores
the plotted angle in strike_rhr_deg (or a unique variant if the name exists).
A missing or invalid dip direction is flagged when that column is selected. To display geographic bearings use a
north-up WGS 84 or Web Mercator project. For other projections, the plotted
angle follows grid north, so convert strike bearings if necessary.

Measurement points appear above existing layers. The optional offline world
basemap supplied by QGIS shows country outlines. For detailed streets or
satellite imagery, add your preferred basemap to the QGIS project.

## Stereonet

Open **Plugins → GeoStructure → Stereonet**. Choose **Plane** or **Line**,
then select **CSV file** or an existing QGIS point layer.

- **Plane**: choose Bedding, Foliation, Joint Plane, or Fault Plane. Map RHR
  strike and dip, or select Dip direction as the plane azimuth and map dip
  direction and dip. Show plane traces, poles, or both.
- **Line**: map trend and downward plunge to plot each linear orientation
  as a point on the stereonet.

CSV files must be UTF-8, comma-separated, and have a header row. Azimuths
are clockwise from north (0–360°); dip and downward plunge are 0–90°.
Orientation-only CSVs need no coordinates. Plane type labels the figure,
so use a separate CSV or filter the QGIS layer for each plane type.
The tool plots one orientation mode at a time.

Click **Save stereoplot…** to export the current lower-hemisphere equal-area
plot as a 1800 × 1800 PNG (300 dpi) or a scalable SVG. Synthetic examples
are provided in example_measurements.csv and example_line_orientations.csv.

### Map symbols in Structural Plot

Choose Plane (Bedding, Foliation, Joint Plane, Fault Plane) or Line
(Lineation, Slickenline, Fold Axis) before mapping your CSV fields. Each
choice has a distinct map symbol. Plane symbols use right-hand-rule strike
and point down-dip. Line arrows point along trend and are labeled with
plunge. These styles are GeoStructure conventions. Each import uses one type.
Line map CSV example:

```csv
station,latitude,longitude,trend,plunge
DEMO-L01,21.990,96.080,45,20
```

## License

GeoStructure is distributed under the GNU General Public License, version 2
or (at your option) any later version. See LICENSE.
