# -*- coding: utf-8 -*-
# alg_step2_culvert_network.py
from qgis.core import (
    QgsProcessingParameterFile, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessing
)
from .alg_base import BaseAlgo, read_manifest, write_manifest, add_to_project
from .cd_helpers import (
    initialise_folders, prepare_inputs, find_road_intersections, create_culvert_network, extract_pour_points
)

class Step2_CulvertNetwork(BaseAlgo):
    def name(self): return "step2_culvert_network"
    def displayName(self): return self.tr("Step 2 – Culvert intersections & empty 1d_nwk")
    def group(self): return self.tr(self.groupId())
    def groupId(self): return ''
    def createInstance(self): return Step2_CulvertNetwork()

    P_BASE="base_folder"; P_ROAD="road"; P_DEM="dem"; P_STREAM="stream_map"
    P_W="road_width"; P_ADD="load_outputs"

    def initAlgorithm(self, config):
        self.addParameter(QgsProcessingParameterFile(self.P_BASE, self.tr("Base folder"),
                                                     behavior=QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterFeatureSource(self.P_ROAD, self.tr("Road batter toes"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterRasterLayer(self.P_DEM, self.tr("DEM")))
        self.addParameter(QgsProcessingParameterRasterLayer(self.P_STREAM, self.tr("Chosen stream map (binary)")))
        self.addParameter(QgsProcessingParameterNumber(self.P_W, self.tr("Approx. road width (m)"),
                                                       QgsProcessingParameterNumber.Double, defaultValue=50, minValue=1))
        self.addParameter(QgsProcessingParameterBoolean(self.P_ADD, self.tr("Load outputs to project?"), defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        base = self.parameterAsFile(parameters, self.P_BASE, context)
        road = self.parameterAsSource(parameters, self.P_ROAD, context)
        dem = self.parameterAsRasterLayer(parameters, self.P_DEM, context)
        stream = self.parameterAsRasterLayer(parameters, self.P_STREAM, context)
        roadw = float(self.parameterAsDouble(parameters, self.P_W, context))
        do_add = bool(self.parameterAsBool(parameters, self.P_ADD, context))

        folders = initialise_folders(base)
        dem_layer, road_layer, _ = prepare_inputs(context, feedback, folders, dem, road)
        inout = find_road_intersections(context, feedback, folders, stream.source(), road_layer)
        nwk = create_culvert_network(context, feedback, folders, dem_layer, inout, roadw)
        pp = extract_pour_points(context, feedback, folders, nwk)

        produced = {"inlets_outlets": inout, "culvert_network": nwk, "pour_points": pp}
        write_manifest(base, produced)
        if do_add:
            add_to_project([inout, nwk, pp])
        return produced