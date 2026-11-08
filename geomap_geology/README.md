# GeoStructure

GeoStructure v0.12.1 for QGIS 3, by Kaung Si Thu.

Map planar and linear structures from CSV, style geological maps, create
Schmidt or Wulff stereonets, analyze orientations and generate DEM cross sections.
The compact Stereonet dialog separates Data, Plot and Analysis tabs.

## 0.12.1 compatibility maintenance

Corrected the 61 unscoped Qt/QGIS enum references reported by the QGIS
repository checker and Cross Section Flake8 E731. This is based on public
0.12.0 and excludes the held 0.13.0 fault-slip draft. No analysis algorithms
were changed. See QT_COMPATIBILITY.md for verification and release limits.

## License

GNU General Public License, version 2 or (at your option) any later version.
See LICENSE. This is an experimental release, tested with QGIS 3.40.6.

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

## Cross Section

Open **Plugins → GeoStructure → Cross Section**. Select a DEM with elevation
in metres in band 1. Optionally select geological polygons, mapped contact
or fault lines, and a bedding point layer with RHR strike and dip fields.
Use **Pick A and A′ on map** to click the two endpoints, then generate the
section. Bedding corridor width is measured from the line to either side.
Positive apparent dip descends toward A′. Projected measurements are drawn
at the DEM elevation on the section, and the CSV records their signed lateral
offsets. The plot reports vertical exaggeration and shows gaps for NoData.

Save the surface section as PNG or SVG, or export profile samples, unit
intervals, mapped line crossings and projected bedding together as CSV.
The section uses a local metric projection and the azimuth from A toward A′.

The map shows A in green and A′ in red, joined by a blue line. The profile
uses bilinear interpolation between DEM pixel centers where all four
neighbors are valid. Near raster edges or NoData, it uses the source sample.

Cross Section includes an optional Station ID field. Choose a station/name
column to identify each projected plane. The result window's Show Label
and Apparent Dip checkbox controls both screen labels and image exports.
Labels show the signed apparent dip in the section, and the CSV includes
station ID, true dip and apparent dip. With no station field, feature IDs
are used. Crowded symbols and labels move to free positions with leader lines.
If the view cannot fit all marks, a message reports the hidden count.

Use Zoom in, Zoom out, and Reset view in the section result window. Mouse
wheel zoom follows the cursor position, and dragging pans horizontally.
The image export uses the current view. CSV export includes the full section.
Structural Analysis has been removed from this release.

## Geological age colors

Geomap Visualizer → Geological age (CGMW / ICS colors) uses an age field.
Supported names include the Phanerozoic periods, the Cenozoic epochs,
Lower/Upper Cretaceous, Lower/Middle/Upper Jurassic and Triassic, and broad
Precambrian, Proterozoic and Archean. Matching ignores case, extra spaces
and underscores. Early/Lower and Late/Upper prefixes are equivalent for
supported subdivisions. Unrecognized values and nulls use gray. Local map
codes (e.g. K1) and combined age ranges must be converted to supported age
names before styling. The dialog lists unrecognized values after applying.
Cross Section reads the resulting polygon colors when regenerated.

Source: CGMW RGB colour code v2022 (ICS 2022/02 subdivisions),
https://ccgm.org/wp-content/uploads/2016/11/Colour-2022-V7-poster.pdf
Carboniferous RGB is clarified using the CGMW 2013 chart,
https://ccgm.org/wp-content/uploads/2016/11/cms_Stratigraphic-Chart_Codes-CMYK_RGB.pdf

## Analysis inside Stereonet

The Analysis selector offers a mean plane (principal pole) and a fold axis /
best-fit girdle for Plane data, or a principal line orientation for Line data.
At least three valid measurements are required. Fits use the normalized
orientation tensor of plane poles or axial line directions. The largest
eigenvector gives the principal pole/line; the smallest gives the normal
to the fitted girdle. Repeated eigenvalues that prevent a unique result
are rejected. The girdle normal can represent a cylindrical fold axis
when bedding poles form a girdle. Other structure types require their own
geological interpretation.

The screen reports normalized eigenvalues and RMS angular deviation
(from the fitted pole/line or from the girdle plane, as appropriate).
Lower-hemisphere fits are shown with a black cross and a purple plane.
PNG/SVG exports include these overlays. Save analysis CSV exports the fit
orientation, eigenvalues, gap, count and RMS deviation. Input filtering
and field selection are the same as the Stereonet plot.
Method reference:
https://mplstereonet.readthedocs.io/en/latest/_modules/mplstereonet/analysis.html

## Joint strike rose and vector mean

In Stereonet choose Plane → Joint Plane, load strike/dip or dip-direction/dip
measurements, then Analysis → Joint strike rose + vector mean. Select 5°,
10°, 15°, 20°, or 30° bins. Strikes are folded to 0–180° and repeated on the
opposite half of the rose. Sector area is proportional to bin count.
The red line is the axial vector mean, calculated by doubling strike
angles, averaging their unit vectors, and halving the resulting angle.
R is the mean resultant length of these doubled angles (0–1).
An effectively zero resultant has no defined mean. This mean summarizes
strike only; it does not estimate mean dip. Mixed joint sets should be
separated before interpreting a single mean. PNG/SVG exports show the rose,
while Save analysis CSV exports the mean, R, count and bin counts.

## Projection and principal orientation axes

On the Plot tab choose Schmidt Net (equal area) or Wulff Net (equal angle).
The projection applies to plane traces, poles, lines and fitted overlays,
including PNG/SVG exports. Rose diagrams retain their polar diagram.
Analytical fits are calculated in three dimensions and are independent
of the display projection.

Analysis → Principal orientation axes reports E1, E2, E3 and their normalized
eigenvalues. These are axes of the orientation tensor, ordered by descending
eigenvalue. Repeated eigenvalues prevent a unique set of three axes and are
reported. E1/E2/E3 describe the measured orientation distribution.
Estimating stress axes requires fault-slip orientations and movement sense,
as well as a stress inversion method and its assumptions.
