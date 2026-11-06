"""Lower-hemisphere equal-area plot of right-hand-rule planes and poles."""

import csv
import math
from pathlib import Path

from qgis.PyQt.QtCore import QIODevice, QPointF, QRect, QSaveFile, QSize, Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from qgis.PyQt.QtSvg import QSvgGenerator
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget,
)
from qgis.core import QgsMapLayerProxyModel, QgsMapLayerType, QgsWkbTypes
from qgis.gui import QgsMapLayerComboBox


def project(east, north, down):
    # Normalized Lambert azimuthal equal-area projection, centered at the nadir.
    scale = math.sqrt(1 + max(0, down))
    return east / scale, north / scale


def plane_and_pole(strike, dip):
    if dip == 0:
        rim = [(math.sin(math.radians(angle)), math.cos(math.radians(angle)))
               for angle in range(0, 361, 4)]
        return rim, (0, 0)
    strike, dip = math.radians(strike), math.radians(dip)
    se, sn = math.sin(strike), math.cos(strike)
    de, dn = sn, -se
    horizontal, down = math.cos(dip), math.sin(dip)
    trace = []
    for step in range(91):
        angle = math.pi * step / 90
        along, across = math.cos(angle), math.sin(angle)
        trace.append(project(along * se + across * horizontal * de,
                             along * sn + across * horizontal * dn,
                             across * down))
    return trace, project(-down * de, -down * dn, horizontal)


def line_point(trend, plunge):
    trend, plunge = math.radians(trend), math.radians(plunge)
    horizontal = math.cos(plunge)
    return project(horizontal * math.sin(trend), horizontal * math.cos(trend), math.sin(plunge))


class Stereonet(QWidget):
    def __init__(self):
        super().__init__()
        self.measurements = []
        self.planes = True
        self.poles = True
        self.structure = "Bedding"
        self.linear = False
        self.setMinimumSize(380, 380)

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw_plot(painter, self.rect())
        painter.end()

    def draw_plot(self, painter, bounds):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(bounds, QColor("white"))
        width, height = bounds.width(), bounds.height()
        painter.setPen(QColor("#25384a"))
        painter.drawText(QRect(0, 5, width, 24), Qt.AlignCenter, f"{self.structure} stereoplot")
        center = QPointF(width / 2, height / 2 - 3)
        radius = min(width - 56, height - 140) / 2

        def screen(east, north):
            return QPointF(center.x() + radius * east, center.y() - radius * north)

        painter.setPen(QPen(QColor("#dde4eb"), 1))
        for plunge in (15, 30, 45, 60, 75):
            ring = radius * math.sqrt(1 - math.sin(math.radians(plunge)))
            painter.drawEllipse(center, ring, ring)
        for azimuth in range(0, 360, 30):
            angle = math.radians(azimuth)
            painter.drawLine(center, screen(math.sin(angle), math.cos(angle)))

        if self.planes:
            painter.setPen(QPen(QColor("#587e9a"), 1))
            for trace, _ in self.measurements:
                painter.drawPolyline(QPolygonF([screen(*point) for point in trace]))
        if self.poles:
            painter.setPen(QPen(QColor("#992c23"), 1))
            painter.setBrush(QColor("#d85344"))
            for _, pole in self.measurements:
                painter.drawEllipse(screen(*pole), 3.3, 3.3)

        if self.linear:
            painter.setPen(QPen(QColor("#126858"), 1))
            painter.setBrush(QColor("#25a58d"))
            for _, point in self.measurements:
                painter.drawEllipse(screen(*point), 3.3, 3.3)

        painter.setBrush(QColor(0, 0, 0, 0))
        painter.setPen(QPen(QColor("#25384a"), 1.3))
        painter.drawEllipse(center, radius, radius)
        for label, east, north in (("N", 0, 1), ("E", 1, 0), ("S", 0, -1), ("W", -1, 0)):
            point = screen(east * (1 + 14 / radius), north * (1 + 14 / radius))
            point.setX(point.x() - painter.fontMetrics().horizontalAdvance(label) / 2)
            point.setY(point.y() + painter.fontMetrics().ascent() / 2)
            painter.drawText(point, label)
        painter.drawText(QRect(0, height - 47, width, 20), Qt.AlignCenter,
                         f"Lower hemisphere · Equal area (Schmidt) · n = {len(self.measurements)}")
        legend = ["Green: line measurements"] if self.linear else []
        if self.planes:
            legend.append("Blue: plane traces")
        if self.poles:
            legend.append("Red: poles")
        painter.drawText(QRect(0, height - 25, width, 20), Qt.AlignCenter, "   |   ".join(legend))

    def save_plot(self, path):
        output = QSaveFile(str(path))
        if not output.open(QIODevice.WriteOnly):
            return False
        bounds = QRect(0, 0, 600, 600)
        if path.suffix.lower() == ".svg":
            device = QSvgGenerator()
            device.setOutputDevice(output)
            device.setSize(QSize(600, 600))
            device.setViewBox(bounds)
            device.setTitle(f"{self.structure} stereoplot")
            scale = 1
        else:
            device = QImage(1800, 1800, QImage.Format_RGB32)
            device.setDotsPerMeterX(11811)
            device.setDotsPerMeterY(11811)
            scale = 3
        painter = QPainter(device)
        if not painter.isActive():
            return False
        painter.scale(scale, scale)
        self.draw_plot(painter, bounds)
        painter.end()
        if scale == 3 and not device.save(output, "PNG"):
            return False
        return output.commit()


class StereoplotDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.setWindowTitle("Stereonet")
        self.resize(650, 740)
        self.form = form = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItems(["Plane", "Line"])
        form.addRow("Orientation", self.mode)
        self.structure = QComboBox()
        self.structure.addItems(["Bedding", "Foliation", "Joint Plane", "Fault Plane"])
        form.addRow("Plane type", self.structure)
        self.source = QComboBox()
        self.source.addItems(["CSV file", "QGIS point layer"])
        form.addRow("Data source", self.source)
        self.file_button = QPushButton("Choose CSV…")
        self.file_button.clicked.connect(self.choose_csv)
        self.file_label = QLabel("No file selected")
        self.file_label.setTextFormat(Qt.PlainText)
        self.file_label.setWordWrap(True)
        self.file_row = QWidget()
        file_layout = QHBoxLayout(self.file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self.file_button)
        file_layout.addWidget(self.file_label, 1)
        form.addRow("CSV", self.file_row)
        self.csv_headers = []
        self.csv_rows = []
        self.csv_invalid = 0
        self.layers = QgsMapLayerComboBox()
        self.layers.setFilters(QgsMapLayerProxyModel.PointLayer)
        form.addRow("Point layer", self.layers)
        self.convention = QComboBox()
        self.convention.addItems(["Right-hand-rule strike", "Dip direction"])
        form.addRow("Plane azimuth", self.convention)
        self.strike = QComboBox()
        self.dip = QComboBox()
        form.addRow("Azimuth field", self.strike)
        form.addRow("Inclination field", self.dip)
        self.structure.currentTextChanged.connect(self.update_visibility)
        self.planes = QCheckBox("Planes (blue)")
        self.poles = QCheckBox("Poles (red)")
        toggles = QHBoxLayout()
        for box in (self.planes, self.poles):
            box.setChecked(True)
            box.toggled.connect(self.update_visibility)
            toggles.addWidget(box)
        self.toggles = QWidget()
        self.toggles.setLayout(toggles)
        form.addRow(self.toggles)
        self.net = Stereonet()
        form.addRow(self.net)
        self.status = QLabel()
        form.addRow(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.export = buttons.addButton("Save stereoplot…", QDialogButtonBox.ActionRole)
        self.export.clicked.connect(self.export_plot)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        for selector in (self.mode, self.source, self.convention):
            selector.currentIndexChanged.connect(self.set_fields)
        self.layers.layerChanged.connect(self.set_fields)
        self.strike.currentIndexChanged.connect(self.refresh_plot)
        self.dip.currentIndexChanged.connect(self.refresh_plot)
        active = iface.activeLayer()
        if active and active.type() == QgsMapLayerType.VectorLayer and active.geometryType() == QgsWkbTypes.PointGeometry:
            self.layers.setLayer(active)
            self.source.setCurrentIndex(1)
        self.set_fields()

    def choose_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open orientation CSV", "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", newline="") as file:
                reader = csv.reader(file, strict=True)
                headers = [name.strip() for name in next(reader, [])]
                if len(headers) < 2 or not all(headers) or len({name.casefold() for name in headers}) != len(headers):
                    raise ValueError("Use at least two nonempty, unique column headers.")
                rows, invalid = [], 0
                for row in reader:
                    if not any(value.strip() for value in row):
                        continue
                    if len(row) == len(headers):
                        rows.append(row)
                    else:
                        invalid += 1
        except (OSError, ValueError, csv.Error) as error:
            QMessageBox.warning(self, "Open orientation CSV", str(error))
            return
        self.csv_headers, self.csv_rows, self.csv_invalid = headers, rows, invalid
        self.file_label.setText(Path(path).name)
        self.set_fields()

    def set_fields(self, *_):
        linear = self.mode.currentText() == "Line"
        from_csv = self.source.currentIndex() == 0
        layer = None if from_csv else self.layers.currentLayer()
        headers = self.csv_headers if from_csv else ([field.name() for field in layer.fields()] if layer else [])
        for widget, visible in (
            (self.file_row, from_csv), (self.layers, not from_csv),
            (self.structure, not linear), (self.convention, not linear), (self.toggles, not linear),
        ):
            widget.setVisible(visible)
            label = self.form.labelForField(widget)
            if label:
                label.setVisible(visible)
        direction = not linear and self.convention.currentIndex() == 1
        self.form.labelForField(self.strike).setText(
            "Trend field" if linear else ("Dip direction field" if direction else "RHR strike field")
        )
        self.form.labelForField(self.dip).setText("Plunge field" if linear else "Dip field")
        if linear:
            azimuth_aliases, inclination_aliases = ("trend", "trend_deg"), ("plunge", "plunge_deg")
        elif direction:
            azimuth_aliases = ("dip_direction", "dip_direction_deg", "dip_dir", "dip_azimuth", "dipdir", "dipdirection")
            inclination_aliases = ("dip", "dip_deg", "dip_angle")
        else:
            azimuth_aliases = ("strike_rhr_deg", "rhr_strike", "strike", "strike_deg", "strik")
            inclination_aliases = ("dip", "dip_deg", "dip_angle")
        fields = {name.casefold().replace(" ", "_"): name for name in headers}
        for selector, aliases, key in (
            (self.strike, azimuth_aliases, "trend_field" if linear else ("" if direction else "rhr_field")),
            (self.dip, inclination_aliases, "plunge_field" if linear else "dip_field"),
        ):
            preferred = layer.customProperty(f"geomap_geology/{key}", "") if layer and key else ""
            name = preferred if preferred in headers else next((fields[alias] for alias in aliases if alias in fields), "")
            selector.blockSignals(True)
            selector.clear()
            selector.addItem("Select field…", None)
            for header in headers:
                selector.addItem(header, header)
            selector.setCurrentIndex(max(0, selector.findData(name)))
            selector.blockSignals(False)
        self.refresh_plot()

    def update_visibility(self):
        self.net.linear = self.mode.currentText() == "Line"
        self.net.planes = not self.net.linear and self.planes.isChecked()
        self.net.poles = not self.net.linear and self.poles.isChecked()
        self.net.structure = "Line" if self.net.linear else self.structure.currentText()
        self.export.setEnabled(bool(self.net.measurements) and
                               (self.net.linear or self.net.planes or self.net.poles))
        self.net.update()

    def export_plot(self):
        png = "PNG image (*.png)"
        svg = "SVG vector graphic (*.svg)"
        name = self.net.structure.lower().replace(" ", "_") + "_stereoplot"
        filename, selected = QFileDialog.getSaveFileName(
            self, "Save stereoplot", name, f"{png};;{svg}", options=QFileDialog.DontConfirmOverwrite,
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() not in (".png", ".svg"):
            path = path.with_name(path.name + (".svg" if selected == svg else ".png"))
        if path.exists() and QMessageBox.question(
            self, "Replace file?", f"Replace {path.name}?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        if not self.net.save_plot(path):
            QMessageBox.warning(self, "Save stereoplot", f"Could not save {path.name}.")

    def refresh_plot(self):
        from_csv = self.source.currentIndex() == 0
        layer = None if from_csv else self.layers.currentLayer()
        azimuth_field, angle_field = self.strike.currentData(), self.dip.currentData()
        linear = self.mode.currentText() == "Line"
        measurements, skipped = [], self.csv_invalid if from_csv else 0
        if azimuth_field and angle_field and azimuth_field != angle_field and (from_csv or layer):
            if from_csv:
                a = self.csv_headers.index(azimuth_field)
                b = self.csv_headers.index(angle_field)
                pairs = ((row[a], row[b]) for row in self.csv_rows)
            else:
                pairs = ((feature[azimuth_field], feature[angle_field]) for feature in layer.getFeatures())
            for bearing, inclination in pairs:
                try:
                    azimuth, angle = float(bearing), float(inclination)
                    if not (0 <= azimuth <= 360 and 0 <= angle <= 90):
                        raise ValueError
                except (TypeError, ValueError):
                    skipped += 1
                    continue
                if linear:
                    measurements.append((None, line_point(azimuth, angle)))
                else:
                    if self.convention.currentIndex() == 1:
                        azimuth = (azimuth - 90) % 360
                    measurements.append(plane_and_pole(azimuth, angle))
            self.status.setText(f"{len(measurements)} valid measurements · {skipped} skipped")
        else:
            self.status.setText("Choose a data source and two separate orientation fields.")
        self.net.measurements = measurements
        self.update_visibility()
