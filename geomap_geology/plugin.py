from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
)
from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsExpression, QgsFillSymbol, QgsLineSymbol,
    QgsMapLayerProxyModel, QgsMarkerSymbol, QgsPalLayerSettings, QgsProperty,
    QgsRendererCategory, QgsSvgMarkerSymbolLayer, QgsVariantUtils,
    QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox


MODES = (
    ("Geological units", QgsMapLayerProxyModel.PolygonLayer, "Unit field"),
    ("Faults", QgsMapLayerProxyModel.LineLayer, "Fault type field"),
    ("Bedding (right-hand-rule strike)", QgsMapLayerProxyModel.PointLayer, "Strike field"),
)
PALETTE = (
    "#e5bd79", "#a9c58f", "#c3afd4", "#eca598", "#90c9d3", "#e4d787",
    "#b2bddd", "#c9ac89", "#f2c6a0", "#94c2ad", "#d5a7c4", "#b5c5ce",
)
FAULT_TYPES = (
    ("Strike-slip", "#2463b6", ("strike slip", "dextral", "sinistral", "right lateral", "left lateral")),
    ("Reverse / thrust", "#c33233", ("reverse", "thrust", "reverse thrust")),
    ("Normal", "#24834e", ("normal", "normal fault")),
)


def categorized(layer, field, faults):
    field_ref = QgsExpression.quotedColumnRef(field)
    if faults:
        normalized = (
            f"trim(regexp_replace(lower(to_string({field_ref})), '[^a-z0-9]+', ' '))"
        )
        cases = []
        categories = []
        for label, color, aliases in FAULT_TYPES:
            values = ", ".join(QgsExpression.quotedString(alias) for alias in aliases)
            cases.append(f"WHEN {normalized} IN ({values}) THEN {QgsExpression.quotedString(label)}")
            symbol = QgsLineSymbol.createSimple({"line_color": color, "line_width": "0.65"})
            categories.append(QgsRendererCategory(label, symbol, label))
        expression = "CASE " + " ".join(cases) + " ELSE 'Other' END"
        fallback = QgsLineSymbol.createSimple(
            {"line_color": "#777777", "line_style": "dash", "line_width": "0.5"}
        )
        categories.append(QgsRendererCategory("Other", fallback, "Other / unspecified"))
    else:
        expression = f"coalesce(nullif(trim(to_string({field_ref})), ''), '')"
        values = sorted({
            str(value).strip() for value in layer.uniqueValues(layer.fields().indexFromName(field))
            if not QgsVariantUtils.isNull(value) and str(value).strip()
        }, key=lambda value: (value.casefold(), value))
        categories = [
            QgsRendererCategory(value, QgsFillSymbol.createSimple({
                "color": PALETTE[index % len(PALETTE)], "outline_color": "#59554c",
                "outline_width": "0.18",
            }), value)
            for index, value in enumerate(values)
        ]
        categories.append(QgsRendererCategory("", QgsFillSymbol.createSimple({
            "color": "#d9d9d9", "outline_color": "#59554c", "outline_width": "0.18",
        }), "Other / unspecified"))
    return QgsCategorizedSymbolRenderer(expression, categories)


def bedding_renderer(field, marker="bedding", label="Bedding strike / dip"):
    strike = QgsExpression.quotedColumnRef(field)
    angle = f"try(to_real({strike}), NULL)"
    valid = f"{angle} >= 0 AND {angle} <= 360"
    svg = QgsSvgMarkerSymbolLayer(str(Path(__file__).with_name(marker + ".svg")), 5)
    symbol = QgsMarkerSymbol()
    symbol.changeSymbolLayer(0, svg)
    symbol.setDataDefinedAngle(QgsProperty.fromExpression(f"CASE WHEN {valid} THEN {angle} END"))
    # Render invalid strike records as dots so they cannot appear as north-striking beds.
    dot = QgsMarkerSymbol.createSimple({"name": "circle", "color": "#777777", "size": "2"})
    return QgsCategorizedSymbolRenderer(
        f"CASE WHEN {valid} THEN 'valid' ELSE 'invalid' END",
        [QgsRendererCategory("valid", symbol, label),
         QgsRendererCategory("invalid", dot, "Missing / invalid azimuth")],
    )


def dip_labels(field):
    settings = QgsPalLayerSettings()
    dip = f"try(to_real({QgsExpression.quotedColumnRef(field)}), NULL)"
    settings.fieldName = f"CASE WHEN {dip} >= 0 AND {dip} <= 90 THEN to_string({dip}) || '°' END"
    settings.isExpression = True
    text = QgsTextFormat()
    text.setSize(9)
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    text.setBuffer(buffer)
    settings.setFormat(text)
    return QgsVectorLayerSimpleLabeling(settings)


class StyleDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Geomap Visualizer")
        self.setMinimumWidth(425)
        self.mode = QComboBox()
        self.mode.addItems([item[0] for item in MODES])
        self.layers = QgsMapLayerComboBox()
        self.field = QgsFieldComboBox()
        self.dip = QgsFieldComboBox()
        self.dip.setAllowEmptyFieldName(True)
        self.form = QFormLayout(self)
        self.form.addRow("Visualization", self.mode)
        self.form.addRow("Map layer", self.layers)
        self.form.addRow("Attribute", self.field)
        self.form.addRow("Dip field (optional)", self.dip)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Apply style")
        self.form.addRow(self.buttons)
        self.buttons.accepted.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        self.layers.layerChanged.connect(self.update_fields)
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def update_mode(self):
        index = self.mode.currentIndex()
        _, geometry, label = MODES[index]
        self.layers.setFilters(geometry)
        self.form.labelForField(self.field).setText(label)
        self.dip.setVisible(index == 2)
        self.form.labelForField(self.dip).setVisible(index == 2)
        self.update_fields()

    def update_fields(self):
        layer = self.layers.currentLayer()
        self.field.setLayer(layer)
        self.dip.setLayer(layer)
        self.dip.setField("")

    def apply(self):
        layer = self.layers.currentLayer()
        field = self.field.currentField()
        if layer is None or not field:
            QMessageBox.warning(self, self.windowTitle(), "Choose a vector layer and an attribute field.")
            return
        mode = self.mode.currentIndex()
        renderer = bedding_renderer(field) if mode == 2 else categorized(layer, field, mode == 1)
        dip = self.dip.currentField() if mode == 2 else ""
        if dip and layer.labelsEnabled():
            answer = QMessageBox.question(
                self, self.windowTitle(), "Replace the current layer labels with dip values?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        layer.setRenderer(renderer)
        if dip:
            layer.setLabeling(dip_labels(dip))
            layer.setLabelsEnabled(True)
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())
        self.iface.messageBar().pushSuccess(self.windowTitle(), f"Styled {layer.name()}")
        self.accept()


class GeologyViewer:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        self.action = QAction("Geomap Visualizer", self.iface.mainWindow())
        self.action.setIcon(QIcon(str(Path(__file__).with_name("visualizer_icon.svg"))))
        self.action.triggered.connect(self.open_dialog)
        self.iface.addPluginToMenu("&GeoStructure", self.action)

        self.csv_action = QAction("Structural Plot", self.iface.mainWindow())
        self.csv_action.setIcon(QIcon(str(Path(__file__).with_name("structural_icon.svg"))))
        self.csv_action.triggered.connect(self.open_csv)
        self.iface.addPluginToMenu("&GeoStructure", self.csv_action)

        self.stereoplot_action = QAction("Stereonet", self.iface.mainWindow())
        self.stereoplot_action.setIcon(QIcon(str(Path(__file__).with_name("stereonet_icon.svg"))))
        self.stereoplot_action.triggered.connect(self.open_stereoplot)
        self.iface.addPluginToMenu("&GeoStructure", self.stereoplot_action)

    def open_stereoplot(self):
        from .stereoplot import StereoplotDialog

        dialog = StereoplotDialog(self.iface)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def open_csv(self):
        from .csv_import import CsvImportDialog

        dialog = CsvImportDialog(self.iface)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def unload(self):
        self.iface.removePluginMenu("&GeoStructure", self.action)
        self.action.deleteLater()
        self.iface.removePluginMenu("&GeoStructure", self.csv_action)
        self.csv_action.deleteLater()
        self.iface.removePluginMenu("&GeoStructure", self.stereoplot_action)
        self.stereoplot_action.deleteLater()

    def open_dialog(self):
        dialog = StyleDialog(self.iface)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()
