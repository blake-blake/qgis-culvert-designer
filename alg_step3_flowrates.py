# -*- coding: utf-8 -*-
# alg_step3_flowrates.py
import gc
import os, json
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterEnum,
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean, QgsProcessingParameterVectorLayer,
    QgsProcessing, QgsVectorLayer, QgsProcessingParameterDefinition
)
import processing
from .alg_base import BaseAlgo, add_to_project, read_manifest, write_manifest
from .cd_helpers import DesignParams, compute_flow_rates, RAIN_METHODS, initialise_folders, delineate_for_pour_points, extract_pour_points

PARAM_SNAP_DIST = 'snap_distance'

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
        defaults = DesignParams()
        
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterEnum(self.P_METHOD, self.tr("Runoff method"),
                                                     options=RAIN_METHODS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(self.P_AREA, self.tr("Area sensitivity factor"),
                                                       QgsProcessingParameterNumber.Double, defaultValue=1.4, minValue=1.0))
        self.addParameter(QgsProcessingParameterVectorLayer(self.P_POUR, self.tr("Pour points or culvert network"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load anything to project?"),
                                                        defaultValue=True))
        param = QgsProcessingParameterNumber(
            PARAM_SNAP_DIST, self.tr('Pour point snap distance (cells/pixels)'),
            QgsProcessingParameterNumber.Double, defaultValue=defaults.snap_distance, minValue=0.0
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        
    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        method = int(self.parameterAsEnum(parameters, self.P_METHOD, context))
        area_factor = float(self.parameterAsDouble(parameters, self.P_AREA, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))
        pour_src = self.parameterAsVectorLayer(parameters, self.P_POUR, context) #pulling this from input not manifest as it may be updated by user
        snap_dist= float(self.parameterAsDouble(parameters, PARAM_SNAP_DIST, context))
        
        mf = read_manifest(base)
        dem_filled = mf.get("filled_dem")
        flowdir = mf.get("flow_dir")
        flowacc = mf.get("flow_acc")
        if not (dem_filled and flowdir and flowacc):
            raise Exception("Filled DEM, flow direction, or flow accumulation not found in manifest. Run Step 1 first.")
        
        folders = initialise_folders(base)
        
        geom_type = pour_src.geometryType()
        if geom_type == 1:
            extracted_pour_points = extract_pour_points(context, feedback, folders, pour_src.source())
            pour_points_path = extracted_pour_points
        elif geom_type == 0:
            pour_points_path = pour_src.source()
        else:
            raise Exception("Unsupported geometry type for pour points/culvert network. Please provide a point layer of pour points or a line layer of the culvert network.")
        
        write_manifest(base, {"pour_points_input": pour_points_path})  # save the path of the pour points used for this step
        
        # Save pour points to file for whitebox (ensure it has an 'ID' field)
        # If not, create a temp autoincrement ID
        src_layer = QgsVectorLayer(pour_points_path, "pour_points", "ogr")

        # strip null geometries before snapping, as whitebox will error on these
        # cleaned = processing.run('native:removenullgeometries', 
        #                          {'INPUT': src_layer, 
        #                           'REMOVE_EMPTY': True, 
        #                           'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        #                           },
        #                           context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
        # src_layer = QgsVectorLayer(cleaned, "pour_points", "ogr")

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
            context, feedback, folders, pour_path, dem_filled, flowdir, flowacc, snap_dist
        )
        
        produced = {
            "processed_ids": ids,
            "catchments": catchments,
            "flowpaths": flowpaths,
            "snapped_pour_points": snapped_pp,
        }

        if do_add:
            add_to_project(catchments + flowpaths)

        flow_by_id = compute_flow_rates(feedback, ids, catchments, flowpaths, method, area_factor)
        
        out_json = os.path.join(folders["culvert"], "flow_by_id.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(flow_by_id, f, indent=2)
        
        produced.update({"flow_by_id": out_json})


        write_manifest(base, produced)
        return produced