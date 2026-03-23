# -*- coding: utf-8 -*-
# alg_step3_flowrates.py
import os, json
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterEnum,
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean, QgsProcessingParameterVectorLayer,
    QgsProcessing, QgsVectorLayer
)
import processing
from .alg_base import BaseAlgo, add_to_project, read_manifest, write_manifest
from .cd_helpers import compute_flow_rates, RAIN_METHODS, initialise_folders

'''
Step 3: Cathcment Delineation & Flow‑rate calculation
- Inputs: catchments/flowpaths
- Outputs: flow rates by catchment ID (json)
'''
class Step3_FlowRates(BaseAlgo):
    def name(self): return "step3_flowrates"
    def displayName(self): return self.tr("Step 3 – Catchment Delineation & Flow‑rate calculation")
    def group(self): return self.tr(self.groupId())
    def groupId(self): return ''
    def createInstance(self): return Step3_FlowRates()

    P_BASE="base_folder"; P_METHOD="rain_method"; P_AREA="area_factor"; P_ADD="load_outputs"; P_POUR="pour_points"; P_SNAP="snap_distance"

    def initAlgorithm(self, config):
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterEnum(self.P_METHOD, self.tr("Runoff method"),
                                                     options=RAIN_METHODS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(self.P_AREA, self.tr("Area sensitivity factor"),
                                                       QgsProcessingParameterNumber.Double, defaultValue=1.4, minValue=1.0))
        self.addParameter(QgsProcessingParameterVectorLayer(self.P_POUR, self.tr("Pour points or culvert network"), [QgsProcessing.TypeVectorAnyGeometry], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load anything to project?"),
                                                        defaultValue=False))
        
    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        method = int(self.parameterAsEnum(parameters, self.P_METHOD, context))
        area = float(self.parameterAsDouble(parameters, self.P_AREA, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))
        pour_src = self.parameterAsVectorLayer(parameters, self.P_POUR, context)
        mf = read_manifest(base)

        folders = initialise_folders(base)
        
        # Save pour points to file for whitebox (ensure it has an 'ID' field)
        # If not, create a temp autoincrement ID
        src_layer = QgsVectorLayer(pour_src.source(), "pour_points", "ogr")
        if src_layer.fields().indexOf('ID') == -1:
            saved = processing.run('native:addautoincrementalfield',
                                    {'FIELD_NAME':'ID','GROUP_FIELDS':[''],'INPUT':src_layer,'MODULUS':0,
                                    'SORT_ASCENDING':True,'SORT_EXPRESSION':None,'SORT_NULLS_FIRST':False,
                                    'START':0,'OUTPUT': os.path.join(folders['pour_points'], 'provided_pour_points.shp')},
                                    context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
            pour_path = saved
        else:
            pour_path = os.path.join(folders['pour_points'], 'provided_pour_points.shp')
            processing.run('native:savefeatures',
                            {'INPUT': src_layer, 'OUTPUT': pour_path, 'LAYER_NAME': 'pour_points'},
                            context=context, feedback=feedback, is_child_algorithm=True)

        ids, catchments, flowpaths, snapped_pp = delineate_for_pour_points(
            context, feedback, folders, pour_path, dem_filled, flowdir, flowacc, snap
        )

        
        produced.update({
            "processed_ids": ids,
            "catchments": catchments,
            "flowpaths": flowpaths,
            "snapped_pour_points": snapped_pp
        })
        if do_add:
            add_to_project(catchments + flowpaths)



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