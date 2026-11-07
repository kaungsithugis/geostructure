"""CGMW RGB colour code v2022, based on the ICS 2022/02 divisions.

Source https://ccgm.org/wp-content/uploads/2016/11/Colour-2022-V7-poster.pdf
Carboniferous RGB is clarified in the CGMW 2013 colour code chart.
"""
import re

from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsExpression, QgsFillSymbol,
    QgsRendererCategory, QgsVariantUtils,
)

AGE_RGB = {
    "Quaternary": (249,249,127),
    "Holocene": (254,235,210),
    "Pleistocene": (255,239,175),
    "Neogene": (255,230,25),
    "Pliocene": (255,255,153),
    "Miocene": (255,255,0),
    "Paleogene": (253,154,82),
    "Oligocene": (253,192,122),
    "Eocene": (253,180,108),
    "Paleocene": (253,167,95),
    "Cretaceous": (127,198,78),
    "Upper Cretaceous": (166,216,74),
    "Lower Cretaceous": (140,205,87),
    "Jurassic": (52,178,201),
    "Upper Jurassic": (179,227,238),
    "Middle Jurassic": (128,207,216),
    "Lower Jurassic": (66,174,208),
    "Triassic": (129,42,146),
    "Upper Triassic": (189,140,195),
    "Middle Triassic": (177,104,177),
    "Lower Triassic": (152,57,153),
    "Permian": (240,64,40),
    "Carboniferous": (103,165,153),
    "Devonian": (203,140,55),
    "Silurian": (179,225,182),
    "Ordovician": (0,146,112),
    "Cambrian": (127,150,86),
    "Precambrian": (247,67,112),
    "Proterozoic": (247,53,99),
    "Archean": (240,4,127),
}
NORMALIZED = {name.casefold(): rgb for name, rgb in AGE_RGB.items()}


def age_rgb(value):
    name = re.sub(r"[_\s]+", " ", value.strip().casefold())
    name = re.sub(r"^early ", "lower ", name)
    name = re.sub(r"^late ", "upper ", name)
    return NORMALIZED.get(name)


def age_renderer(layer, field):
    categories, unmatched = [], []
    values = sorted({
        str(value).strip() for value in layer.uniqueValues(layer.fields().indexFromName(field))
        if not QgsVariantUtils.isNull(value) and str(value).strip()
    }, key=str.casefold)
    for value in values:
        rgb = age_rgb(value)
        if rgb is None:
            unmatched.append(value)
        color = ",".join(map(str, rgb or (217,217,217)))
        symbol = QgsFillSymbol.createSimple({
            "color": color, "outline_color": "#59554c", "outline_width": "0.18",
        })
        categories.append(QgsRendererCategory(value,symbol,value))
    fallback = QgsFillSymbol.createSimple({
        "color": "#d9d9d9", "outline_color": "#59554c", "outline_width": "0.18",
    })
    categories.append(QgsRendererCategory("",fallback,"Unknown / unspecified"))
    expression = f"coalesce(nullif(trim(to_string({QgsExpression.quotedColumnRef(field)})), ''), '')"
    return QgsCategorizedSymbolRenderer(expression,categories), unmatched
