"""Axial strike rose and doubled-angle vector mean."""

import math

from qgis.PyQt.QtCore import QPointF, QRect, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen


def strike_summary(strikes, width):
    if not strikes:
        raise ValueError("Load valid plane measurements first.")
    values = [strike % 180 for strike in strikes]
    counts = [0] * (180 // width)
    for strike in values:
        counts[int(strike // width)] += 1
    c = sum(math.cos(math.radians(2 * value)) for value in values) / len(values)
    s = sum(math.sin(math.radians(2 * value)) for value in values) / len(values)
    resultant = math.hypot(c, s)
    mean = (math.degrees(math.atan2(s, c)) / 2) % 180 if resultant > 1e-8 else None
    if mean is not None and math.isclose(mean, 180, abs_tol=1e-8):
        mean = 0.0
    return {
        "method": "Joint strike rose and axial vector mean", "n": len(values),
        "bin_width_deg": width, "axial_mean_strike_deg": mean,
        "opposite_strike_deg": (mean + 180) if mean is not None else None,
        "mean_resultant_length": resultant,
        "bins": counts,
    }


def draw_rose(painter, bounds, result):
    width, height = bounds.width(), bounds.height()
    painter.fillRect(bounds, QColor("white"))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    center = QPointF(width/2, height/2)
    radius = min(width, height)/2 - 65
    counts, bin_width = result["bins"], result["bin_width_deg"]
    maximum = max(counts)
    painter.setPen(QColor("#233444"))
    painter.drawText(QRect(0, 5, width, 25), Qt.AlignmentFlag.AlignCenter, "Joint strike rose · axial")
    def point(angle, length):
        angle = math.radians(angle)
        return center + QPointF(math.sin(angle)*length, -math.cos(angle)*length)
    for fraction in (0.25, 0.5, 0.75, 1):
        painter.setPen(QPen(QColor("#cbd5dd"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius*fraction, radius*fraction)
    painter.setPen(QPen(QColor("#365c76"), 1))
    painter.setBrush(QColor("#8db7cf"))
    for i, count in enumerate(counts):
        if count == 0:
            continue
        length = radius * math.sqrt(count/maximum)
        for opposite in (0, 180):
            start = i*bin_width + opposite
            path = QPainterPath(center)
            path.lineTo(point(start, length))
            for step in range(1, 21):
                path.lineTo(point(start + bin_width*step/20, length))
            path.closeSubpath()
            painter.drawPath(path)
    mean = result["axial_mean_strike_deg"]
    if mean is not None:
        painter.setPen(QPen(QColor("#bb3030"), 2))
        painter.drawLine(point(mean, radius), point(mean+180, radius))
    painter.setPen(QColor("#233444"))
    for text, angle in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        painter.drawText(point(angle, radius+16)+QPointF(-5, 5), text)
    painter.drawText(QRect(0, height-49, width, 20), Qt.AlignmentFlag.AlignCenter,
                     f"n = {result['n']} · bin {bin_width}° · outer ring count {maximum}")
    painter.drawText(QRect(0, height-27, width, 20), Qt.AlignmentFlag.AlignCenter,
                     "Red: axial vector mean · sector area ∝ count · opposite bins repeated")
