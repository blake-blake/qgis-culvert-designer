# -*- coding: utf-8 -*-
# alg_step1_hydro.py
import os
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessing, QgsVectorLayer
)
import processing
from .alg_base import BaseAlgo, read_manifest, write_manifest, add_to_project
from .cd_helpers import (
    initialise_folders, prepare_inputs, whitebox_flow_preparation, delineate_for_pour_points
)

class Step1_Hydro(BaseAlgo):
    def name(self): return "step1_hydro"
    def displayName(self): return self.tr("Step 1 – Hydrology prep & create empty 1d_nwk")
    def group(self): return self.tr(self.groupId())
    def groupId(self): return ''
    def createInstance(self): return Step1_Hydro()

    P_BASE="base_folder"; P_DEM="dem"; 
    P_EXIST="existing_ldd_map"
    P_POUR="pour_points"; P_SNAP="snap_distance"; P_ADD="load_outputs"

    def initAlgorithm(self, config):
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterRasterLayer(self.P_DEM, self.tr("DEM (1–5 m)")))
        # self.addParameter(QgsProcessingParameterFile(self.P_EXIST, self.tr("Existing lddcreate.map (optional)"),
        #                                              behavior=QgsProcessingParameterFile.File, optional=True,
        #                                              fileFilter="PCRaster MAP (*.map)"))
        # self.addParameter(QgsProcessingParameterVectorLayer(self.P_POUR, self.tr("Pour points (optional)"),
        #                                                       [QgsProcessing.TypeVectorPoint], optional=True))
        # self.addParameter(QgsProcessingParameterNumber(self.P_SNAP, self.tr("Snap distance (cells)"),
        #                                                QgsProcessingParameterNumber.Double, defaultValue=2.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load outputs to project?"), defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        dem = self.parameterAsRasterLayer(parameters, self.P_DEM, context)
        # existing_ldd = (self.parameterAsFile(parameters, self.P_EXIST, context) or "").strip()
        # pour_src = self.parameterAsVectorLayer(parameters, self.P_POUR, context)
        # snap = float(self.parameterAsDouble(parameters, self.P_SNAP, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))

        folders = initialise_folders(base)
        _, _, dem_clean_tif = prepare_inputs(context, feedback, folders, dem, None)
        
        # Always prepare whitebox rasters (fill, dir, acc)
        dem_filled, flowdir, flowacc, _, poly_streams = whitebox_flow_preparation(dem_clean_tif, folders)
        
        
        produced = {
            "base_folder": base,
            "dem": dem.source(),
            # "lddcreate": ldd,
            # "max_strahler": int(max_order),
            "filled_dem": dem_filled, 
            "flow_dir": flowdir, 
            "flow_acc": flowacc
        }

        add_to_project([poly_streams] if do_add else [])
        

        write_manifest(base, produced)
        return produced