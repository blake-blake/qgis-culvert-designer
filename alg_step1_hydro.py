# -*- coding: utf-8 -*-
# alg_step1_hydro.py

from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterRasterLayer,
        QgsProcessingParameterBoolean)


from .alg_base import BaseAlgo, read_manifest, write_manifest, add_to_project
from .cd_helpers import (
    initialise_folders, prepare_inputs, whitebox_flow_preparation
)
'''
Step 1: Hydrology prep & stream network creation
- Inputs: DEM (1–5 m)
- Outputs: stream network (vector)
'''
class Step1_Hydro(BaseAlgo):
    def name(self): return "step1_hydro"
    def displayName(self): return self.tr("Step 1 – Hydrology prep & stream network creation")
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
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load outputs to project?"), defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        dem = self.parameterAsRasterLayer(parameters, self.P_DEM, context)
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))

        folders = initialise_folders(base)
        _, _, dem_clean_tif = prepare_inputs(context, feedback, folders, dem, None)
        
        dem_filled, flowdir, flowacc, _, streams_vector = whitebox_flow_preparation(dem_clean_tif, folders)


        produced = {
            "base_folder": base,
            "dem": dem.source(),
            "filled_dem": dem_filled, 
            "flow_dir": flowdir, 
            "flow_acc": flowacc,
            "streams_vector": streams_vector
        }

        add_to_project([streams_vector] if do_add else [])
        
        write_manifest(base, produced)
        return produced