"""Axial orientation fits from a normalized orientation tensor."""

import math

import numpy as np


def lower(vector):
    vector = np.asarray(vector, dtype=float)
    if vector[2] < -1e-12 or (
        abs(vector[2]) <= 1e-12 and (vector[1] < -1e-12 or
                                   (abs(vector[1]) <= 1e-12 and vector[0] < 0))
    ):
        vector = -vector
    return vector


def trend_plunge(vector):
    east, north, down = lower(vector)
    plunge = math.degrees(math.asin(float(np.clip(down, -1, 1))))
    trend = math.degrees(math.atan2(east, north)) % 360
    return (0.0 if math.isclose(trend, 360, abs_tol=1e-9) else trend), max(0, plunge)


def analyze(orientations, linear, method):
    if len(orientations) < 3:
        raise ValueError("At least three valid measurements are required.")
    vectors = []
    for azimuth, angle in orientations:
        trend = azimuth if linear else (azimuth - 90) % 360
        plunge = angle if linear else 90 - angle
        t, p = math.radians(trend), math.radians(plunge)
        vectors.append([math.cos(p)*math.sin(t), math.cos(p)*math.cos(t), math.sin(p)])
    vectors = np.array(vectors)
    eigenvalues, eigenvectors = np.linalg.eigh(vectors.T @ vectors / len(vectors))
    eigenvalues = np.clip(eigenvalues, 0, 1)
    girdle = method == "Fold axis / best-fit girdle"
    index = 0 if girdle else 2
    gap = eigenvalues[1] - eigenvalues[0] if girdle else eigenvalues[2] - eigenvalues[1]
    if method == "Principal orientation axes":
        if min(eigenvalues[1]-eigenvalues[0], eigenvalues[2]-eigenvalues[1]) < 1e-6:
            raise ValueError("Repeated eigenvalues: all three orientation axes are not uniquely defined.")
    if gap < 1e-6:
        raise ValueError("This dataset does not define a unique fitted orientation.")
    vector = lower(eigenvectors[:, index])
    trend, plunge = trend_plunge(vector)
    dots = np.clip(np.abs(vectors @ vector), 0, 1)
    deviations = np.arcsin(dots) if girdle else np.arccos(dots)
    rms = float(np.degrees(np.sqrt(np.mean(deviations**2))))
    result = {
        "method": method, "n": len(vectors), "trend_deg": trend, "plunge_deg": plunge,
        "rms_deviation_deg": rms, "lambda1": float(eigenvalues[2]),
        "lambda2": float(eigenvalues[1]), "lambda3": float(eigenvalues[0]),
        "eigenvalue_gap": float(gap),
    }
    for number, column in enumerate((2,1,0),1):
        axis_trend, axis_plunge = trend_plunge(eigenvectors[:,column])
        result[f"axis{number}_trend_deg"] = axis_trend
        result[f"axis{number}_plunge_deg"] = axis_plunge
    if not linear or girdle:
        result["strike_rhr_deg"] = (trend + 90) % 360
        if math.isclose(result["strike_rhr_deg"], 360, abs_tol=1e-9):
            result["strike_rhr_deg"] = 0.0
        result["dip_deg"] = 90 - plunge
    return result
