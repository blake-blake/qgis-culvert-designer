# -*- coding: utf-8 -*-
# alg_step1_hydro.py
import os
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterFeatureSource, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessing, QgsVectorLayer
)
import processing
from .alg_base import BaseAlgo, read_manifest, write_manifest, add_to_project
from .cd_helpers import (
    initialise_folders, prepare_inputs, create_ldd, create_streamorder,
    whitebox_prepare, delineate_for_pour_points
)

class Step1_Hydro(BaseAlgo):
    def name(self): return "step1_hydro"
    def displayName(self): return self.tr("Step 1 – Hydrology prep & (optional) catchments/streams")
    def group(self): return self.tr(self.groupId())
    def groupId(self): return ''
    def createInstance(self): return Step1_Hydro()

    P_BASE="base_folder"; P_DEM="dem"; P_EXIST="existing_ldd_map"
    P_POUR="pour_points"; P_SNAP="snap_distance"; P_ADD="load_outputs"

    def initAlgorithm(self, config):
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterRasterLayer(self.P_DEM, self.tr("DEM (1–5 m)")))
        self.addParameter(QgsProcessingParameterFile(self.P_EXIST, self.tr("Existing lddcreate.map (optional)"),
                                                     behavior=QgsProcessingParameterFile.File, optional=True,
                                                     fileFilter="PCRaster MAP (*.map)"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.P_POUR, self.tr("Pour points (optional)"),
                                                              [QgsProcessing.TypeVectorPoint], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.P_SNAP, self.tr("Snap distance (cells)"),
                                                       QgsProcessingParameterNumber.Double, defaultValue=2.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load outputs to project?"), defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        dem = self.parameterAsRasterLayer(parameters, self.P_DEM, context)
        existing_ldd = (self.parameterAsFile(parameters, self.P_EXIST, context) or "").strip()
        pour_src = self.parameterAsSource(parameters, self.P_POUR, context)
        snap = float(self.parameterAsDouble(parameters, self.P_SNAP, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))

        folders = initialise_folders(base)
        dem_layer, _, pcr_map = prepare_inputs(context, feedback, folders, dem, None)
        ldd = create_ldd(context, feedback, folders, pcr_map, existing_ldd)
        max_order = create_streamorder(context, feedback, folders, ldd)

        produced = {
            "base_folder": base,
            "dem": dem.source(),
            "lddcreate": ldd,
            "max_strahler": int(max_order)
        }

        # Always prepare whitebox rasters (fill, dir, acc)
        dem_filled, flowdir, flowacc = whitebox_prepare(context, feedback, folders, dem_layer)
        produced.update({"filled_dem": dem_filled, "flow_dir": flowdir, "flow_acc": flowacc})

        # Optional: if pour points provided, run delineation now
        if pour_src:
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

        write_manifest(base, produced)
        return produced