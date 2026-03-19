# -*- coding: utf-8 -*-
# alg_step3_flowrates.py
import os, json
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterEnum,
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean
)
from .alg_base import BaseAlgo, read_manifest, write_manifest
from .cd_helpers import compute_flow_rates, RAIN_METHODS

class Step3_FlowRates(BaseAlgo):
    def name(self): return "step3_flowrates"
    def displayName(self): return self.tr("Step 3 – Flow‑rate calculation")
    def group(self): return self.tr(self.groupId())
    def groupId(self): return ''
    def createInstance(self): return Step3_FlowRates()

    P_BASE="base_folder"; P_METHOD="rain_method"; P_AREA="area_factor"; P_ADD="load_outputs"

    def initAlgorithm(self, config):
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterEnum(self.P_METHOD, self.tr("Runoff method"),
                                                     options=RAIN_METHODS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(self.P_AREA, self.tr("Area sensitivity factor"),
                                                       QgsProcessingParameterNumber.Double, defaultValue=1.4, minValue=1.0))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load anything to project?"),
                                                        defaultValue=False))

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        method = int(self.parameterAsEnum(parameters, self.P_METHOD, context))
        area = float(self.parameterAsDouble(parameters, self.P_AREA, context))

        mf = read_manifest(base)
        ids = mf.get("processed_ids")
        cats = mf.get("catchments")
        flows = mf.get("flowpaths")
        if not (ids and cats and flows):
            raise Exception("Catchments/flowpaths not found. Run Step 1 with pour points (or Step 2 then Step 1) first.")

        flow_by_id = compute_flow_rates(feedback, ids, cats, flows, method, area)
        out_json = os.path.join(base, "CulvertNetwork", "flow_by_id.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(flow_by_id, f, indent=2)
        write_manifest(base, {"flow_by_id": out_json})
        return {"flow_by_id": out_json}