"""Import a field-measurement CSV and save the plotted points to a GeoPackage."""

import csv
import math
from pathlib import Path

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QMessageBox, QPushButton,
)
from qgis.core import (
    QgsApplication, QgsCoordinateTransform, QgsCsException, QgsFeature, QgsField, QgsFillSymbol,
    QgsGeometry, QgsPointXY, QgsProject, QgsRectangle, QgsVectorFileWriter,
    QgsVectorLayer,
)

from .plugin import bedding_renderer, dip_labels


PLANE_SYMBOLS = {"Bedding": "bedding", "Foliation": "foliation", "Joint Plane": "joint",
                 "Fault Plane": "fault_plane"}
LINE_SYMBOLS = {"Lineation": "lineation", "Slickenline": "slickenline", "Fold Axis": "fold_axis"}

COLUMNS = (
    ("Latitude", ("latitude", "lat", "y")),
    ("Longitude", ("longitude", "lon", "long", "lng", "x")),
    ("Strike (RHR if no dip direction)", ("strike", "strike_deg", "rhr_strike", "strik")),
    ("Dip", ("dip", "dip_deg", "dip_angle")),
    ("Dip direction (optional)", ("dip_direction", "dip_direction_deg", "dip_dir", "dip_azimuth", "dipdir", "dipdirection")),
)
LINE_COLUMNS = COLUMNS[:2] + (
    ("Trend", ("trend", "trend_deg")), ("Plunge", ("plunge", "plunge_deg")),
)
LIMITS = ((-90, 90), (-180, 180), (0, 360), (0, 90), (0, 360))


def load_points(path, headers, indices, linear=False):
    layer = QgsVectorLayer("Point?crs=EPSG:4326", Path(path).stem, "memory")
    provider = layer.dataProvider()
    latitude_index, longitude_index, strike_index, dip_index, direction_index = indices
    used = {name.casefold() for name in headers}
    rhr_field = "trend_plot_deg" if linear else "strike_rhr_deg"
    while rhr_field.casefold() in used:
        rhr_field = "_" + rhr_field
    numeric_indices = {latitude_index, longitude_index, dip_index}
    numeric_indices.add(direction_index if direction_index >= 0 else strike_index)
    provider.addAttributes([
        QgsField(name, QVariant.Double if index in numeric_indices else QVariant.String)
        for index, name in enumerate(headers)
    ] + [QgsField(rhr_field, QVariant.Double)])
    layer.updateFields()
    features, rejected = [], []
    with open(path, encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        if [name.strip() for name in next(reader, [])] != headers:
            raise ValueError("The CSV header changed. Select the file again.")
        for row in reader:
            if not any(value.strip() for value in row):
                continue
            try:
                if len(row) != len(headers):
                    raise ValueError
                for index, (low, high) in zip(indices, LIMITS):
                    if index not in numeric_indices:
                        continue
                    value = float(row[index])
                    if not math.isfinite(value) or not low <= value <= high:
                        raise ValueError
                    row[index] = value
            except ValueError:
                rejected.append(reader.line_num)
                continue
            latitude, longitude = row[latitude_index], row[longitude_index]
            strike = (row[direction_index] - 90) if direction_index >= 0 else row[strike_index]
            row.append(strike % 360)
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(longitude, latitude)))
            feature.setAttributes(row)
            features.append(feature)
    if not features:
        raise ValueError("No valid rows. Check column mapping, decimal degrees, and orientation ranges.")
    if not provider.addFeatures(features)[0]:
        raise ValueError("QGIS could not create the measurement points.")
    layer.updateExtents()
    return layer, rejected, rhr_field


class CsvImportDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.path = ""
        self.headers = []
        self.setWindowTitle("Structural Plot")
        self.setMinimumWidth(470)
        self.form = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItems(["Plane", "Line"])
        self.form.addRow("Orientation", self.mode)
        self.structure = QComboBox()
        self.form.addRow("Structure type", self.structure)
        select = QPushButton("Choose CSV…")
        select.clicked.connect(self.select_file)
        self.form.addRow(select)
        self.filename = QLabel("No CSV selected")
        self.form.addRow(self.filename)
        self.selectors = []
        for label, _ in COLUMNS:
            combo = QComboBox()
            self.form.addRow(label, combo)
            self.selectors.append(combo)
        note = QLabel("Use WGS 84 decimal degrees. Dip direction takes precedence when selected. "
                      "For geographic bearings, use a north-up WGS 84 or Web Mercator map.")
        note.setWordWrap(True)
        self.form.addRow(note)
        self.world = QCheckBox("Add offline world basemap beneath project layers")
        self.world.setChecked(not QgsProject.instance().mapLayers())
        self.form.addRow(self.world)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.plot = buttons.button(QDialogButtonBox.Ok)
        self.plot.setText("Save and plot")
        self.plot.setEnabled(False)
        buttons.accepted.connect(self.import_points)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)
        self.mode.currentIndexChanged.connect(self.set_mode)
        self.set_mode()

    def set_mode(self):
        linear = self.mode.currentIndex() == 1
        self.structure.clear()
        self.structure.addItems(LINE_SYMBOLS if linear else PLANE_SYMBOLS)
        direction = self.selectors[4]
        direction.setVisible(not linear)
        self.form.labelForField(direction).setVisible(not linear)
        self.populate_fields()

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select measurements", "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", newline="") as source:
                headers = [name.strip() for name in next(csv.reader(source, strict=True), [])]
            if len(headers) < 4 or not all(headers) or len({h.casefold() for h in headers}) != len(headers):
                raise ValueError("Use at least four nonempty, unique column headers.")
        except (OSError, ValueError, csv.Error) as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
            return
        self.path, self.headers = path, headers
        self.filename.setText(Path(path).name)
        self.populate_fields()

    def populate_fields(self):
        headers = self.headers
        linear = self.mode.currentIndex() == 1
        normalized = [name.casefold().replace(" ", "_") for name in headers]
        for combo, (label, aliases) in zip(self.selectors, LINE_COLUMNS if linear else COLUMNS):
            self.form.labelForField(combo).setText(label)
            combo.clear()
            combo.addItem("None" if not linear and combo in (self.selectors[2], self.selectors[4]) else "Select column…")
            combo.addItems(headers)
            match = next((normalized.index(alias) + 1 for alias in aliases if alias in normalized), 0)
            combo.setCurrentIndex(match)
        self.plot.setEnabled(bool(headers))

    def import_points(self):
        indices = [combo.currentIndex() - 1 for combo in self.selectors]
        linear = self.mode.currentIndex() == 1
        if linear:
            indices[4] = -1
        try:
            latitude, longitude, strike, dip, direction = indices
            selected = [index for index in indices if index >= 0]
            if min(latitude, longitude, dip) < 0 or max(strike, direction) < 0:
                raise ValueError("Select latitude, longitude, trend, and plunge." if linear else
                                 "Select latitude, longitude, dip, and either strike or dip direction.")
            if len(set(selected)) != len(selected):
                raise ValueError("Select a different CSV column for each field.")
            source, rejected, rhr_field = load_points(self.path, self.headers, indices, linear)
            if rejected:
                sample = ", ".join(map(str, rejected[:8]))
                answer = QMessageBox.question(
                    self, self.windowTitle(),
                    f"Skip {len(rejected)} invalid record(s)? Affected CSV lines include {sample}.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
            output, _ = QFileDialog.getSaveFileName(
                self, "Save measurement layer", str(Path(self.path).with_suffix(".gpkg")),
                "GeoPackage (*.gpkg)", options=QFileDialog.DontConfirmOverwrite,
            )
            if not output:
                return
            target = Path(output)
            if target.suffix.lower() != ".gpkg":
                target = target.with_name(target.name + ".gpkg")
            if target.exists():
                raise ValueError("Choose a new GeoPackage filename to avoid overwriting existing data.")
            self.plot_points(source, target, rhr_field, self.headers[dip])
        except (OSError, ValueError, csv.Error) as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
            return
        self.accept()

    def plot_points(self, source, target, rhr_field, dip_field):
        project = QgsProject.instance()
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = "structural_measurements"
        # Avoid a collision with the GeoPackage primary key or geometry column.
        used = {name.casefold() for name in self.headers}
        layer_options = []
        for name in ("fid", "geom"):
            candidate = name
            while candidate in used:
                candidate = "_" + candidate
            layer_options.append(f"{'FID' if name == 'fid' else 'GEOMETRY_NAME'}={candidate}")
        options.layerOptions = layer_options
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            source, str(target), project.transformContext(), options,
        )
        if result[0] != QgsVectorFileWriter.NoError:
            raise ValueError(f"Could not save the GeoPackage. {result[1]}")
        layer = QgsVectorLayer(f"{target}|layername={options.layerName}", source.name(), "ogr")
        if not layer.isValid():
            raise ValueError("The GeoPackage was written but QGIS could not reopen it.")
        linear = self.mode.currentIndex() == 1
        structure = self.structure.currentText()
        symbol = (LINE_SYMBOLS if linear else PLANE_SYMBOLS)[structure]
        layer.setRenderer(bedding_renderer(rhr_field, symbol, structure))
        azimuth_key, angle_key = ("trend_field", "plunge_field") if linear else ("rhr_field", "dip_field")
        layer.setCustomProperty(f"geomap_geology/{azimuth_key}", rhr_field)
        layer.setCustomProperty(f"geomap_geology/{angle_key}", dip_field)
        layer.setLabeling(dip_labels(dip_field))
        layer.setLabelsEnabled(True)
        if self.world.isChecked():
            self.add_world_map(project)
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self.iface.setActiveLayer(layer)
        canvas = self.iface.mapCanvas()
        transform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(), project)
        extent = QgsRectangle(layer.extent())
        if extent.isEmpty():
            extent.grow(0.002)
        extent.scale(1.2)
        try:
            canvas.setExtent(transform.transformBoundingBox(extent))
            canvas.refresh()
        except QgsCsException:
            self.iface.messageBar().pushWarning(self.windowTitle(), "Imported points. Zoom to the layer manually.")
        self.iface.messageBar().pushSuccess(self.windowTitle(), f"Plotted {layer.featureCount()} measurements")

    def add_world_map(self, project):
        path = Path(QgsApplication.pkgDataPath()) / "resources" / "data" / "world_map.gpkg"
        if any(layer.source().split("|", 1)[0] == str(path) for layer in project.mapLayers().values()):
            return
        world = QgsVectorLayer(str(path), "World basemap (QGIS)", "ogr")
        if not world.isValid():
            self.iface.messageBar().pushWarning(self.windowTitle(), "Offline world basemap unavailable in this QGIS installation.")
            return
        world.renderer().setSymbol(QgsFillSymbol.createSimple({
            "color": "#e8ebdc", "outline_color": "#9ca69b", "outline_width": "0.18",
        }))
        project.addMapLayer(world, False)
        project.layerTreeRoot().addLayer(world)
