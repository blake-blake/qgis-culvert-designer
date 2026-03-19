# -*- coding: utf-8 -*-
# alg_base.py
import os
import json
import inspect
from datetime import datetime
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProject, QgsVectorLayer, QgsRasterLayer,
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication

MANIFEST_NAME = "CulvertDesign.manifest.json"

def manifest_path(base_folder: str) -> str:
    return os.path.join(base_folder, MANIFEST_NAME)

def read_manifest(base_folder: str) -> dict:
    try:
        with open(manifest_path(base_folder), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_manifest(base_folder: str, data: dict):
    os.makedirs(base_folder, exist_ok=True)
    path = manifest_path(base_folder)
    merged = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                merged = json.load(f)
        except Exception:
            merged = {}
    merged.update(data or {})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)

def add_to_project(paths_or_layers):
    for obj in paths_or_layers:
        if isinstance(obj, str):
            p = obj
            if p.lower().endswith((".tif", ".tiff")):
                QgsProject.instance().addMapLayer(QgsRasterLayer(p, os.path.basename(p)))
            else:
                QgsProject.instance().addMapLayer(QgsVectorLayer(p, os.path.basename(p), "ogr"))
        else:
            QgsProject.instance().addMapLayer(obj)

class BaseAlgo(QgsProcessingAlgorithm):
    def tr(self, s): return QCoreApplication.translate('Processing', s)

    def icon(self):
        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        return QIcon(os.path.join(cmd_folder, 'icon.jpg'))

    def log(self, feedback, message):
        from datetime import datetime
        now = datetime.now()
        text = f"✏️ [{now.strftime('%H:%M:%S')}] {message}"
        if feedback is not None:
            feedback.pushInfo(text)
        print(text)