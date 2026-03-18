# -*- coding: utf-8 -*-
# alg_step4_size_culverts.py
import os, json, shutil
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean,
    QgsVectorLayer
)
from .alg_base import BaseAlgo, read_manifest, write_manifest, add_to_project
from .cd_helpers import DesignParams, size_culverts_HDS5

class Step4_SizeCulverts(BaseAlgo):
    def name(self): return "step4_sizeculverts"
    def displayName(self): return self.tr("Step 4 – Culvert sizing & 1d_nwk update")
    def group(self): return self.tr(self.groupId())
    def groupId(self): return ''
    def createInstance(self): return Step4_SizeCulverts()

    P_BASE="base_folder"; P_NWK="nwk_layer"; P_HW="headwater_limit"; P_N="mannings_n"; P_ADD="load_outputs"

    def initAlgorithm(self, config):
        d = DesignParams()
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterFeatureSource(self.P_NWK, self.tr("1d_nwk layer (optional)"),
                                                              [0], optional=True))  # 0 = line layer
        self.addParameter(QgsProcessingParameterNumber(self.P_HW, self.tr("Max allowable Hw/D"),
                                                       QgsProcessingParameterNumber.Double,
                                                       defaultValue=d.headwater_limit, minValue=0.1))
        self.addParameter(QgsProcessingParameterNumber(self.P_N, self.tr("Manning’s n (CMP)"),
                                                       QgsProcessingParameterNumber.Double,
                                                       defaultValue=d.mannings_n, minValue=0.01, maxValue=0.2))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load updated network to project?"), defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        hw = float(self.parameterAsDouble(parameters, self.P_HW, context))
        nval = float(self.parameterAsDouble(parameters, self.P_N, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))
        mf = read_manifest(base)

        flow_json = mf.get("flow_by_id")
        if not flow_json or not os.path.exists(flow_json):
            raise Exception("flow_by_id.json not found. Run Step 3 first.")
        with open(flow_json, "r", encoding="utf-8") as f:
            flow_by_id = json.load(f)

        layer_param = self.parameterAsSource(parameters, self.P_NWK, context)
        if layer_param:
            nwk_path = layer_param.source()
        else:
            nwk_path = mf.get("culvert_network")
            if not nwk_path or not os.path.exists(nwk_path):
                raise Exception("1d_nwk not provided and not found in manifest. Run Step 2 first or select a layer.")

        sized_path = os.path.join(base, "CulvertNetwork", "1d_nwk_sized.shp")
        # copy shapefile group
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            src = nwk_path.replace(".shp", ext)
            dst = sized_path.replace(".shp", ext)
            if os.path.exists(src):
                shutil.copy(src, dst)

        vlay = QgsVectorLayer(sized_path, "1d_nwk_sized", "ogr")
        processed_ids = [int(k) for k in flow_by_id.keys()]
        d = DesignParams()
        size_culverts_HDS5(feedback, processed_ids, vlay, flow_by_id, d.pipe_diameters_m, hw, nval)

        write_manifest(base, {"culvert_network_sized": sized_path})
        if do_add:
            add_to_project([sized_path])
        return {"culvert_network_sized": sized_path}