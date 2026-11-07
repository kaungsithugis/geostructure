"""Build a surface section from a DEM and optional geological layers."""

import csv
import math
from functools import lru_cache
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, QRect, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QPen
from qgis.PyQt.QtSvg import QSvgGenerator
from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest,
    QgsRenderContext, QgsExpressionContext, QgsExpressionContextUtils,
    QgsGeometry, QgsGeometryCollection, QgsMapLayerProxyModel, QgsPointXY, QgsProject, QgsWkbTypes,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox, QgsMapToolEmitPoint, QgsRubberBand, QgsVertexMarker


def apparent_dip(dip, direction, section_azimuth):
    """Positive angles descend toward A′, negative angles descend toward A."""
    angle = math.radians(dip)
    component = math.cos(math.radians(direction - section_azimuth))
    if abs(component) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(math.sin(angle) * component, math.cos(angle)))


def elevation_sampler(provider):
    """Interpolate adjacent DEM pixel centers without filling NoData gaps."""
    extent = provider.extent()
    columns, rows = provider.xSize(), provider.ySize()
    width = extent.width() / columns if columns else 0
    height = extent.height() / rows if rows else 0

    def read(point):
        value, ok = provider.sample(point, 1)
        return value if ok and math.isfinite(value) else None

    @lru_cache(maxsize=4096)
    def pixel(column, row):
        return read(QgsPointXY(extent.xMinimum() + (column + 0.5) * width,
                               extent.yMaximum() - (row + 0.5) * height))

    def sample(point):
        if width <= 0 or height <= 0 or not extent.contains(point):
            return read(point)
        x = (point.x() - extent.xMinimum()) / width
        y = (extent.yMaximum() - point.y()) / height
        column, row = math.floor(x - 0.5), math.floor(y - 0.5)
        if not (0 <= column < columns - 1 and 0 <= row < rows - 1):
            return read(point)
        values = [pixel(column, row), pixel(column + 1, row),
                  pixel(column, row + 1), pixel(column + 1, row + 1)]
        if any(value is None for value in values):
            return read(point)
        dx, dy = x - 0.5 - column, y - 0.5 - row
        upper = (1 - dx) * values[0] + dx * values[1]
        lower = (1 - dx) * values[2] + dx * values[3]
        return (1 - dy) * upper + dy * lower

    return sample


def build_section(start, end, canvas_crs, dem, count, corridor, units, unit_field,
                  faults, bedding, strike_field, dip_field, station_field=""):
    project = QgsProject.instance()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    origin = QgsCoordinateTransform(canvas_crs, wgs84, project).transform(start)
    local = QgsCoordinateReferenceSystem.fromProj(
        f"+proj=aeqd +lat_0={origin.y()} +lon_0={origin.x()} +datum=WGS84 +units=m"
    )
    to_local = QgsCoordinateTransform(canvas_crs, local, project)
    a, b = to_local.transform(start), to_local.transform(end)
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length < 0.01:
        raise ValueError("Choose two different endpoints.")
    ux, uy = dx / length, dy / length
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    section = QgsGeometry.fromPolylineXY([a, b])
    raster_transform = QgsCoordinateTransform(local, dem.crs(), project)
    elevation_at = elevation_sampler(dem.dataProvider())

    def sample(distance):
        point = QgsPointXY(a.x() + ux * distance, a.y() + uy * distance)
        return elevation_at(raster_transform.transform(point))

    def position(point):
        x, y = point.x() - a.x(), point.y() - a.y()
        return x * ux + y * uy, -x * uy + y * ux

    def features(layer, width):
        bounds = section.boundingBox()
        bounds.grow(max(0.01, width))
        to_layer = QgsCoordinateTransform(local, layer.crs(), project)
        to_section = QgsCoordinateTransform(layer.crs(), local, project)
        request = QgsFeatureRequest().setFilterRect(to_layer.transformBoundingBox(bounds))
        for feature in layer.getFeatures(request):
            geometry = feature.geometry()
            if geometry.isEmpty():
                continue
            geometry.transform(to_section)
            yield feature, geometry

    def parts(geometry):
        if geometry.isEmpty():
            return
        children = geometry.asGeometryCollection() if isinstance(geometry.constGet(), QgsGeometryCollection) else []
        if children:
            for child in children:
                yield from parts(child)
        else:
            yield geometry

    profile = [(i * length / (count - 1), sample(i * length / (count - 1))) for i in range(count)]
    if not any(z is not None for _, z in profile):
        raise ValueError("The DEM returned no elevations along this section.")
    intervals, crossings, measurements = [], [], []
    if units:
        context = QgsRenderContext()
        expression = QgsExpressionContext()
        expression.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(units))
        context.setExpressionContext(expression)
        renderer = units.renderer().clone()
        renderer.startRender(context, units.fields())
        try:
            for feature, geometry in features(units, 0):
                context.expressionContext().setFeature(feature)
                symbol = renderer.symbolForFeature(feature, context)
                if symbol is None:
                    continue
                color = QColor(symbol.color())
                color.setAlphaF(color.alphaF() * symbol.opacity() * units.opacity())
                name = str(feature[unit_field]) if unit_field else str(feature.id())
                for part in parts(geometry.intersection(section)):
                    distances = [position(point)[0] for point in part.vertices()]
                    if distances and max(distances) - min(distances) > 0.001:
                        intervals.append((min(distances), max(distances), name, color.name(QColor.HexArgb)))
        finally:
            renderer.stopRender(context)
    if faults:
        for feature, geometry in features(faults, 0):
            for part in parts(geometry.intersection(section)):
                distances = [position(point)[0] for point in part.vertices()]
                if distances:
                    for distance in sorted({min(distances), max(distances)}):
                        crossings.append((distance, sample(distance), feature.id()))
    if bedding:
        for feature, geometry in features(bedding, corridor):
            try:
                strike, dip = float(feature[strike_field]), float(feature[dip_field])
            except (TypeError, ValueError):
                continue
            if not (0 <= strike <= 360 and 0 <= dip <= 90):
                continue
            for point in geometry.vertices():
                distance, offset = position(point)
                if 0 <= distance <= length and abs(offset) <= corridor:
                    measurements.append((distance, sample(distance), feature.id(), offset, strike, dip,
                                         apparent_dip(dip, (strike + 90) % 360, bearing),
                                         str(feature[station_field]) if station_field else str(feature.id())))
    return profile, sorted(intervals), sorted(crossings, key=lambda row: row[0]), sorted(measurements, key=lambda row: row[0]), bearing


class SectionPlot(QWidget):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.labels = True
        self.view_start = 0.0
        self.view_end = data[0][-1][0]
        self.drag_x = None
        self.hidden_count = 0
        self.layout_boxes = []
        self.setMouseTracking(True)
        self.setMinimumSize(720, 380)

    def zoom(self, factor, fraction=0.5):
        total = self.data[0][-1][0]
        fraction = max(0.0, min(1.0, fraction))
        span = self.view_end - self.view_start
        anchor = self.view_start + span * fraction
        new_span = min(total, max(total / 1000, span / factor))
        self.set_view(anchor - new_span * fraction, new_span)

    def set_view(self, start, span):
        total = self.data[0][-1][0]
        self.view_start = min(max(0, start), total - span)
        self.view_end = self.view_start + span
        self.update()

    def reset_view(self):
        self.set_view(0, self.data[0][-1][0])

    def wheelEvent(self, event):
        fraction = (event.pos().x() - 72) / max(1, self.width() - 108)
        self.zoom(1.35 if event.angleDelta().y() > 0 else 1 / 1.35, fraction)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_x = event.pos().x()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag_x is not None:
            span = self.view_end - self.view_start
            shift = (self.drag_x - event.pos().x()) * span / max(1, self.width() - 108)
            self.drag_x = event.pos().x()
            self.set_view(self.view_start + shift, span)

    def mouseReleaseEvent(self, event):
        self.drag_x = None
        self.unsetCursor()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw(painter, self.width(), self.height())
        painter.end()

    def draw(self, painter, width, height):
        profile, units, faults, bedding, bearing = self.data
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(0, 0, width, height, QColor("white"))
        left, right, top, bottom = 72, width - 36, 54, height - 96
        visible = lambda distance: self.view_start <= distance <= self.view_end
        elevations = [z for distance, z in profile if z is not None and visible(distance)]
        elevations += [row[1] for row in faults + bedding if row[1] is not None and visible(row[0])]
        if not elevations:
            elevations = [z for _, z in profile if z is not None]
        low, high = min(elevations), max(elevations)
        pad = max(1, (high - low) * 0.15)
        low, high = low - pad, high + pad
        sx, sy = (right-left)/(self.view_end-self.view_start), (bottom-top)/(high-low)

        def point(distance, elevation):
            return QPointF(left + sx * (distance-self.view_start), bottom - sy * (elevation - low))

        painter.setPen(QColor("#233444"))
        painter.drawText(left, 26, f"A–A′  |  Azimuth {bearing:05.1f}°  |  Vertical exaggeration {sy/sx:.2f}×")
        painter.drawText(8, top - 10, "Elevation")
        for i in range(5):
            elevation = low + (high-low)*i/4
            y = point(0, elevation).y()
            painter.setPen(QColor("#dce3e8"))
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            painter.setPen(QColor("#233444"))
            painter.drawText(QPointF(8, y+4), f"{elevation:.1f}")
            distance = self.view_start+(self.view_end-self.view_start)*i/4
            painter.drawText(QPointF(left + sx*(distance-self.view_start) - 12, bottom+18), f"{distance:.0f}")
        painter.drawText(left, bottom+38, "A   ·   Distance along section (m)   ·   A′")
        painter.save()
        painter.setClipRect(QRectF(left, top, right-left, bottom-top))
        painter.setPen(QPen(QColor("#223e4f"), 2))
        previous = None
        for distance, elevation in profile:
            current = None if elevation is None else point(distance, elevation)
            if previous is not None and current is not None:
                painter.drawLine(previous, current)
            previous = current
        painter.setPen(QPen(QColor("#b42c36"), 2))
        for distance, elevation, _ in faults:
            if elevation is not None:
                p = point(distance, elevation)
                painter.drawLine(p + QPointF(0, -8), p + QPointF(0, 8))
        # Keep measurements anchored to their true locations. Move crowded
        # symbols and labels together and connect them with a leader line.
        boxes = []
        self.hidden_count = 0
        metrics = painter.fontMetrics()
        for distance, elevation, _, _, _, true_dip, dip, station in bedding:
            if elevation is None or not visible(distance):
                continue
            anchor = point(distance, elevation)
            text = f"{station}  {dip:.1f}°"
            text_width = metrics.horizontalAdvance(text) if self.labels else 0
            box_width = 27 + text_width
            box_height = max(25, metrics.height() + 10)
            candidates = [QPointF(0, 0)]
            for ring in range(1, max(2, int((bottom-top)/box_height))):
                for dx in (0, -box_width, box_width):
                    for dy in (-ring*box_height, ring*box_height):
                        candidates.append(QPointF(dx,dy))
            placed = None
            for offset in candidates:
                center = anchor + offset
                rectangle = QRectF(center.x()-12,center.y()-box_height/2,box_width,box_height)
                if rectangle.left()<left or rectangle.right()>right or rectangle.top()<top or rectangle.bottom()>bottom:
                    continue
                if not any(rectangle.intersects(box) for box in boxes):
                    placed = (center,rectangle)
                    break
            if placed is None:
                self.hidden_count += 1
                continue
            center,rectangle = placed
            boxes.append(rectangle)
            if center != anchor:
                painter.setPen(QPen(QColor("#8396a8"), 0.8))
                painter.drawLine(anchor,center)
                painter.setBrush(QColor("#245eb0"))
                painter.drawEllipse(anchor,2,2)
            angle = math.radians(dip)
            vx, vy = math.cos(angle)*sx, math.sin(angle)*sy
            scale = 9/math.hypot(vx, vy)
            delta = QPointF(vx*scale, vy*scale)
            painter.setPen(QPen(QColor("#245eb0"), 2))
            painter.drawLine(center-delta,center+delta)
            if self.labels:
                label_rect = QRectF(center.x()+13,center.y()-metrics.height()/2,
                                    text_width+2,metrics.height()+2)
                painter.fillRect(label_rect,QColor(255,255,255,230))
                painter.drawText(label_rect,Qt.AlignLeft | Qt.AlignVCenter,text)
        self.layout_boxes = boxes
        painter.restore()
        for start, end, name, color in units:
            start, end = max(start,self.view_start), min(end,self.view_end)
            if end <= start:
                continue
            x, span = left+(start-self.view_start)*sx, (end-start)*sx
            painter.fillRect(int(x), bottom+46, max(1,int(span)), 17, QColor(color))
            if painter.fontMetrics().horizontalAdvance(name) + 4 < span:
                painter.setPen(QColor("#233444"))
                painter.drawText(QPointF(x+2,bottom+59), name)
        painter.setPen(QColor("#233444"))
        caption = "Red: crossings · Blue: bedding · Band: mapped geological units"
        if self.hidden_count:
            caption = f"{self.hidden_count} crowded marks hidden — zoom in or turn labels off"
        painter.drawText(left, height-10, caption)

    def export(self, filename):
        width, height = 1100, 570
        if filename.lower().endswith(".svg"):
            output = QSvgGenerator()
            output.setFileName(filename)
            output.setSize(QSize(width,height))
            output.setViewBox(QRect(0,0,width,height))
        else:
            output = QImage(width*2,height*2,QImage.Format_RGB32)
        painter = QPainter(output)
        if not painter.isActive():
            raise ValueError("Could not open the image output.")
        if isinstance(output, QImage):
            painter.scale(2,2)
        self.draw(painter,width,height)
        painter.end()
        if isinstance(output,QImage) and not output.save(filename):
            raise ValueError("Could not save the PNG.")


class CrossSectionDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.setWindowTitle("Cross Section")
        self.canvas = iface.mapCanvas()
        self.endpoints = []
        self.markers = []
        self.section_line = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.section_line.setColor(QColor("#245eb0"))
        self.section_line.setWidth(2)
        self.canvas.destinationCrsChanged.connect(self.draw_section_line)
        self.tool = QgsMapToolEmitPoint(self.canvas)
        self.tool.canvasClicked.connect(self.capture)
        self.previous_tool = None
        self.capture_crs = None
        self.setAttribute(Qt.WA_DeleteOnClose)
        form = QFormLayout(self)
        self.dem = self.layer(form,"Elevation raster in metres (band 1)",QgsMapLayerProxyModel.RasterLayer,False)
        self.units = self.layer(form,"Geological units",QgsMapLayerProxyModel.PolygonLayer)
        self.unit_field = QgsFieldComboBox()
        self.units.layerChanged.connect(self.unit_field.setLayer)
        form.addRow("Unit name field",self.unit_field)
        self.faults = self.layer(form,"Fault or contact lines",QgsMapLayerProxyModel.LineLayer)
        self.bedding = self.layer(form,"Bedding measurements",QgsMapLayerProxyModel.PointLayer)
        self.strike, self.dip = QgsFieldComboBox(), QgsFieldComboBox()
        self.bedding.layerChanged.connect(self.bedding_fields)
        form.addRow("RHR strike field",self.strike)
        form.addRow("Dip field",self.dip)
        self.station = QgsFieldComboBox()
        self.station.setAllowEmptyFieldName(True)
        form.addRow("Station ID field (optional)",self.station)
        self.corridor = QSpinBox()
        self.corridor.setRange(0,100000)
        self.corridor.setValue(250)
        self.corridor.setSuffix(" m")
        form.addRow("Corridor half-width",self.corridor)
        self.samples = QSpinBox()
        self.samples.setRange(2,10000)
        self.samples.setValue(600)
        form.addRow("DEM samples",self.samples)
        self.status = QLabel("Choose A and A′ on the map. Elevations are interpolated from the DEM.")
        form.addRow(self.status)
        for title, callback in (("Pick A and A′ on map",self.pick),("Generate section",self.generate)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            form.addRow(button)

    def layer(self, form, label, geometry, optional=True):
        selector = QgsMapLayerComboBox()
        selector.setFilters(geometry)
        selector.setAllowEmptyLayer(optional)
        if optional:
            selector.setLayer(None)
        form.addRow(label,selector)
        return selector

    def bedding_fields(self, layer):
        self.station.setLayer(layer)
        names = {field.name().casefold(): field.name() for field in layer.fields()} if layer else {}
        self.station.setField(next((names[name] for name in ("station","station_id","id","name") if name in names), ""))
        for selector,key,fallback in ((self.strike,"rhr_field","strike_rhr_deg"),(self.dip,"dip_field","dip")):
            selector.setLayer(layer)
            if layer:
                preferred = layer.customProperty(f"geomap_geology/{key}",fallback)
                selector.setField(preferred if layer.fields().indexFromName(preferred) >= 0 else
                                  ("strike" if selector == self.strike else fallback))

    def pick(self):
        self.restore_tool()
        self.endpoints.clear()
        self.draw_section_line()
        self.capture_crs = self.canvas.mapSettings().destinationCrs()
        self.previous_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.tool)
        self.status.setText("Click A on the map, then click A′.")

    def capture(self, point, button):
        if button == Qt.RightButton:
            self.endpoints.clear()
            self.draw_section_line()
            self.restore_tool()
            self.status.setText("Endpoint selection canceled.")
        elif button == Qt.LeftButton:
            current = self.canvas.mapSettings().destinationCrs()
            point = QgsCoordinateTransform(current,self.capture_crs,QgsProject.instance()).transform(point)
            self.endpoints.append(point)
            self.draw_section_line()
            if len(self.endpoints) == 2:
                self.restore_tool()
                self.status.setText("A (green) and A′ (red) set. Generate the section.")
            else:
                self.status.setText("A (green) set. Click A′.")

    def draw_section_line(self):
        for marker in self.markers:
            self.canvas.scene().removeItem(marker)
        self.markers.clear()
        self.section_line.reset(QgsWkbTypes.LineGeometry)
        if not self.endpoints:
            return
        transform = QgsCoordinateTransform(self.capture_crs, self.canvas.mapSettings().destinationCrs(),
                                           QgsProject.instance())
        for endpoint, color in zip(self.endpoints, ("#237a47", "#b42c36")):
            point = transform.transform(endpoint)
            marker = QgsVertexMarker(self.canvas)
            marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
            marker.setIconSize(12)
            marker.setPenWidth(2)
            marker.setColor(QColor("white"))
            marker.setFillColor(QColor(color))
            marker.setCenter(point)
            self.markers.append(marker)
            self.section_line.addPoint(point)

    def restore_tool(self):
        if self.canvas.mapTool() == self.tool:
            if self.previous_tool:
                self.canvas.setMapTool(self.previous_tool)
            else:
                self.canvas.unsetMapTool(self.tool)
        self.previous_tool = None

    def done(self, result):
        self.restore_tool()
        self.canvas.destinationCrsChanged.disconnect(self.draw_section_line)
        self.endpoints.clear()
        self.draw_section_line()
        self.canvas.scene().removeItem(self.section_line)
        super().done(result)

    def generate(self):
        dem, bedding = self.dem.currentLayer(), self.bedding.currentLayer()
        strike, dip = self.strike.currentField(), self.dip.currentField()
        try:
            if len(self.endpoints) != 2 or not dem:
                raise ValueError("Select a DEM and pick two endpoints.")
            if bedding and (not strike or not dip or strike == dip):
                raise ValueError("Choose separate RHR strike and dip fields.")
            data = build_section(*self.endpoints,self.capture_crs,dem,self.samples.value(),
                                 self.corridor.value(),self.units.currentLayer(),self.unit_field.currentField(),
                                 self.faults.currentLayer(),bedding,strike,dip,self.station.currentField())
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self,"Cross Section",str(error))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Cross Section A–A′")
        dialog.resize(920,510)
        layout = QVBoxLayout(dialog)
        plot = SectionPlot(data)
        layout.addWidget(plot,1)
        labels = QCheckBox("Show Label and Apparent Dip")
        labels.setChecked(True)
        labels.toggled.connect(lambda enabled: self.toggle_labels(plot, enabled))
        layout.addWidget(labels)
        controls = QHBoxLayout()
        for title, callback in (("Zoom in", lambda: plot.zoom(1.5)),
                                ("Zoom out", lambda: plot.zoom(1/1.5)),
                                ("Reset view", plot.reset_view)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        layout.addWidget(QLabel("Mouse wheel to zoom · Drag left/right to pan · Image export uses current view"))
        layout.addWidget(QLabel(f"{len(data[1])} unit intervals · {len(data[2])} crossings · {len(data[3])} projected measurements"))
        for title, callback in (
            ("Save PNG or SVG…", lambda: self.save_image(plot)),
            ("Save section CSV…", lambda: self.save_csv(data)),
        ):
            button = QPushButton(title)
            button.clicked.connect(callback)
            layout.addWidget(button)
        dialog.exec()
        dialog.deleteLater()

    def toggle_labels(self, plot, enabled):
        plot.labels = enabled
        plot.update()

    def save_image(self, plot):
        path, selected = QFileDialog.getSaveFileName(self,"Save section","section","PNG (*.png);;SVG (*.svg)")
        if path:
            suffix = ".svg" if selected.startswith("SVG") else ".png"
            if Path(path).suffix.lower() not in (".png",".svg"):
                path += suffix
            try:
                plot.export(path)
            except (ValueError,OSError) as error:
                QMessageBox.warning(self,"Save section",str(error))

    def save_csv(self,data):
        path, _ = QFileDialog.getSaveFileName(self,"Save section data","section.csv","CSV (*.csv)")
        if not path:
            return
        try:
            with open(path,"w",newline="",encoding="utf-8") as output:
                writer = csv.writer(output)
                writer.writerow(["record_type","distance_m","end_distance_m","elevation_dem_units","unit",
                                 "feature_id","signed_offset_m","strike_rhr_deg","dip_deg","apparent_dip_deg","station_id"])
                for distance,z in data[0]:
                    writer.writerow(["profile",distance,"",z,"","","","","",""])
                for start,end,unit,_color in data[1]:
                    writer.writerow(["unit",start,end,"",unit,"","","","",""])
                for distance,z,fid in data[2]:
                    writer.writerow(["crossing",distance,"",z,"",fid,"","","",""])
                for distance,z,fid,offset,strike,dip,apparent,station in data[3]:
                    writer.writerow(["bedding",distance,"",z,"",fid,offset,strike,dip,apparent,station])
        except OSError as error:
            QMessageBox.warning(self,"Save section data",str(error))
