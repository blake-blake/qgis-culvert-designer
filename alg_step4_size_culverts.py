# -*- coding: utf-8 -*-
# alg_step4_size_culverts.py
import os, json, shutil
import pandas as pd
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
        self.addParameter(QgsProcessingParameterFeatureSource(self.P_NWK, self.tr("1d_nwk layer"),
                                                              [0], optional=True))  # 0 = line layer
        self.addParameter(QgsProcessingParameterNumber(self.P_HW, self.tr("Max allowable Hw/D"),
                                                       QgsProcessingParameterNumber.Double,
                                                       defaultValue=d.headwater_limit, minValue=0.1))
        self.addParameter(QgsProcessingParameterNumber(self.P_N, self.tr("Manning’s n (CMP)"),
                                                       QgsProcessingParameterNumber.Double,
                                                       defaultValue=d.mannings_n, minValue=0.01, maxValue=0.2))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load updated network to project?"), defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        coeffs = pd.read_excel(os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources/Rating_cruves/culvert_coefficients.xlsx"), sheet_name="coeffs", index_col=0) 

        base = self.parameterAsFile(parameters, self.P_BASE, context)
        hw = float(self.parameterAsDouble(parameters, self.P_HW, context))
        nval = float(self.parameterAsDouble(parameters, self.P_N, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))
        mf = read_manifest(base)

        ids = mf.get("processed_ids")
        cats = mf.get("catchments")
        flows = mf.get("flowpaths")
        if not (ids and cats and flows):
            raise Exception("Catchments/flowpaths not found. Run Step 1 with pour points (or Step 2 then Step 1) first.")


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

    def evaluate_poly(Q, A, B, C, D):
        return A * Q**3 + B * Q**2 + C * Q + D

    def interpolate_coefficients(coeffs, diameter, slope, prefix, length = 20):
        # Filter coefficients for the given diameter
        table = coeffs[coeffs['Diameter'] == diameter]
        # table = coeffs[(coeffs["Diameter"] == diameter) & (coeffs["Length"] == length)]

        if table.empty:
            raise ValueError(f"No coefficients found for diameter {diameter}")

        available_slopes = sorted(table['Slope'].unique())

        # if exact slope exists, return the coefficients directly
        if slope in available_slopes:
            row = table[table['Slope'] == slope].iloc[0]
            A, B, C, D = row[f'{prefix}_A'], row[f'{prefix}_B'], row[f'{prefix}_C'], row[f'{prefix}_D']
            return A, B, C, D

        lower_slope = max(s for s in available_slopes if s < slope)
        upper_slope = min(s for s in available_slopes if s > slope)

        row1 = table[table['Slope'] == lower_slope].iloc[0]
        row2 = table[table['Slope'] == upper_slope].iloc[0]

        factor = (slope - lower_slope) / (upper_slope - lower_slope)

        A = row1[f'{prefix}_A'] + factor * (row2[f'{prefix}_A'] - row1[f'{prefix}_A'])
        B = row1[f'{prefix}_B'] + factor * (row2[f'{prefix}_B'] - row1[f'{prefix}_B'])
        C = row1[f'{prefix}_C'] + factor * (row2[f'{prefix}_C'] - row1[f'{prefix}_C'])
        D = row1[f'{prefix}_D'] + factor * (row2[f'{prefix}_D'] - row1[f'{prefix}_D'])

        return A, B, C, D

    def calculate_culvert(Q, diameter, slope, length, coeffs):

        length = 20  # fixed length for rating curves for now

        hw_coeffs = interpolate_coefficients(coeffs, diameter, slope, length, prefix="HW")
        hwd_coeffs = interpolate_coefficients(coeffs, diameter, slope, length, prefix="HWD")
        v_coeffs = interpolate_coefficients(coeffs, diameter, slope, length, prefix="V")

        hw = evaluate_poly(Q, *hw_coeffs)
        hwd = evaluate_poly(Q, *hwd_coeffs)
        velocity = evaluate_poly(Q, *v_coeffs)
        
        return hw, hwd, velocity

    def size_culvert(Q, slope, length, max_hwd, max_velocity, coeffs):
        for diameter in sorted(coeffs['Diameter'].unique()):
            hw, hwd, velocity = calculate_culvert(Q, diameter, slope, length, coeffs)
            if hwd <= max_hwd and velocity <= max_velocity:
                return {"diameter": diameter, "hw": round(hw, 3), "hwd": round(hwd, 3), "velocity": round(velocity, 3)}
        return None