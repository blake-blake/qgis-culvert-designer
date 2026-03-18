# -*- coding: utf-8 -*-
# cd_helpers.py
import os, io, sys, math, shutil, csv, inspect
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple, List, Dict

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing, QgsVectorLayer, QgsRasterLayer, QgsField, QgsGeometry,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
    QgsProcessingException
)
import processing

# External libs used in your original code
import pcraster as pcr
from whitebox import WhiteboxTools

# ----------------------------
# Constants & Params
# ----------------------------
RAIN_METHODS = ['Flavels RFFP2000 (Pilbara)', 'Rational (basic, global)']

@dataclass(frozen=True)
class DesignParams:
    headwater_limit: float = 1.5
    mannings_n: float = 0.024
    snap_distance: float = 2.0
    area_factor: float = 1.4
    pipe_diameters_m: Tuple[float, ...] = (3.2, 2.4, 2.1, 1.8, 1.2, 0.9, 0.6)

# ----------------------------
# Folder initialisation
# ----------------------------
def initialise_folders(base_folder: str) -> dict:
    os.makedirs(base_folder, exist_ok=True)
    folders = {
        "base": base_folder,
        "whitebox": os.path.join(base_folder, "Whitebox"),
        "catchments": os.path.join(base_folder, "Whitebox", "Catchments"),
        "pour_points": os.path.join(base_folder, "Whitebox", "PourPoints"),
        "stream_paths": os.path.join(base_folder, "Whitebox", "StreamPaths"),
        "pcraster": os.path.join(base_folder, "PCRaster"),
        "qgis": os.path.join(base_folder, "QGISIntermediates"),
        "lddcreate": os.path.join(base_folder, "PCRaster", "Lddcreate"),
        "strahler": os.path.join(base_folder, "PCRaster", "StrahlerOrders"),
        "culvert": os.path.join(base_folder, "CulvertNetwork")
    }
    for f in folders.values():
        os.makedirs(f, exist_ok=True)
    return folders

# ----------------------------
# I/O preparations
# ----------------------------
def prepare_inputs(context, feedback, folders: dict, dem_layer, road_layer=None):
    """
    - Validates DEM, names it 'DEM' (for raster_value expressions),
    - Reprojects road layer to DEM CRS if provided,
    - Converts DEM to PCRaster map for later PCR operations.
    """
    if sys.stdout is None: sys.stdout = sys.__stdout__ or io.StringIO()
    if sys.stderr is None: sys.stderr = sys.__stderr__ or io.StringIO()

    if not dem_layer or not dem_layer.isValid():
        raise ValueError('DEM is invalid or not provided')
    dem_layer.setName("DEM")
    dem_crs = dem_layer.crs()

    if road_layer and road_layer.isValid() and (road_layer.crs() != dem_crs):
        alg_params = {
            'CONVERT_CURVED_GEOMETRIES': False,
            'INPUT': road_layer,
            'OPERATION': '',
            'TARGET_CRS': dem_crs,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        out = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        road_layer = out['OUTPUT']

    pcr_map = os.path.join(folders['pcraster'], 'pcraster_dem.map')
    processing.run('pcraster:converttopcrasterformat',
                   {'INPUT': dem_layer, 'INPUT2': 3, 'OUTPUT': pcr_map},
                   context=context, feedback=feedback, is_child_algorithm=True)

    return dem_layer, road_layer, pcr_map

# ----------------------------
# PCRaster stream order
# ----------------------------
def create_ldd(context, feedback, folders, dem_pcr_map_path: str, existing_ldd: str):
    ldd_out = os.path.join(folders['lddcreate'], 'lddcreate.map')
    existing_ldd = (existing_ldd or "").strip()
    if existing_ldd:
        src = Path(existing_ldd)
        dst = Path(ldd_out)
        if not src.exists():
            raise QgsProcessingException(f"Existing LDD not found: {src}")
        if src.resolve() != dst.resolve():
            shutil.copy(existing_ldd, ldd_out)
    else:
        processing.run('pcraster:lddcreate',
                       {
                           'INPUT': dem_pcr_map_path,
                           'INPUT0': 0,
                           'INPUT1': 0,  # Map units
                           'INPUT2': 9999999,
                           'INPUT3': 9999999,
                           'INPUT4': 9999999,
                           'INPUT5': 9999999,
                           'OUTPUT': ldd_out
                       },
                       context=context, feedback=feedback, is_child_algorithm=True)
    return ldd_out

def create_streamorder(context, feedback, folders, ldd_map_path: str):
    strahler_map = os.path.join(folders['pcraster'], 'strahler_order.map')
    processing.run('pcraster:streamorder',
                   {'INPUT': ldd_map_path, 'OUTPUT': strahler_map},
                   context=context, feedback=feedback, is_child_algorithm=True)

    # build per-order maps
    pcr.setclone(strahler_map)
    strahler = pcr.readmap(strahler_map)
    max_strahler_raster = pcr.mapmaximum(strahler)
    max_value = int(pcr.cellvalue(max_strahler_raster, 0, 0)[0])

    for order in range(1, max_value + 1):
        stream = pcr.ifthen(strahler >= order, pcr.boolean(1))
        pcr.report(stream, os.path.join(folders['strahler'], f'stream{order}.map'))
    return max_value

# ----------------------------
# Intersections & culvert scaffolding
# ----------------------------
def find_road_intersections(context, feedback, folders, stream_map_path: str, road_layer):
    # polygonize stream raster
    poly_stream = os.path.join(folders['qgis'], 'Polygonized_StreamPath.shp')
    processing.run('gdal:polygonize',
                   {'BAND': 1, 'EIGHT_CONNECTEDNESS': False, 'EXTRA': None, 'FIELD': 'DN',
                    'INPUT': stream_map_path, 'OUTPUT': poly_stream},
                   context=context, feedback=feedback, is_child_algorithm=True)

    # intersection
    inter_lines = os.path.join(folders['qgis'], 'intersections_line.shp')
    processing.run('native:intersection',
                   {'GRID_SIZE': None, 'INPUT': road_layer, 'INPUT_FIELDS': [''],
                    'OVERLAY': poly_stream, 'OVERLAY_FIELDS': [''],
                    'OVERLAY_FIELDS_PREFIX': None, 'OUTPUT': inter_lines},
                   context=context, feedback=feedback, is_child_algorithm=True)

    # convert line→point (centroids)
    inter_points = os.path.join(folders['qgis'], 'intersections_point.shp')
    processing.run('native:centroids',
                   {'ALL_PARTS': False, 'INPUT': inter_lines, 'OUTPUT': inter_points},
                   context=context, feedback=feedback, is_child_algorithm=True)

    # merge duplicates by buffering, dissolving, centroid
    buf = processing.run('native:buffer',
                         {'DISSOLVE': False, 'DISTANCE': 1, 'END_CAP_STYLE': 2,
                          'INPUT': inter_points, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2,
                          'SEGMENTS': 5, 'SEPARATE_DISJOINT': False,
                          'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                         context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    dis = processing.run('native:dissolve',
                         {'FIELD': [''], 'INPUT': buf, 'SEPARATE_DISJOINT': True,
                          'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                         context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    cen = processing.run('native:centroids',
                         {'ALL_PARTS': True, 'INPUT': dis, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                         context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    merged_points = os.path.join(folders['qgis'], 'inlets_and_outlets.shp')
    processing.run('native:deleteduplicategeometries',
                   {'INPUT': cen, 'OUTPUT': merged_points},
                   context=context, feedback=feedback, is_child_algorithm=True)

    return merged_points

def create_culvert_network(context, feedback, folders, dem_layer, road_intersections_path: str, road_width_m: float):
    # group inlets/outlets within approx road width
    buf2 = processing.run('native:buffer',
                          {'DISSOLVE': False, 'DISTANCE': road_width_m/2 + 10, 'END_CAP_STYLE': 0,
                           'INPUT': road_intersections_path, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2, 'SEGMENTS': 5,
                           'SEPARATE_DISJOINT': False, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                          context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    dis2 = processing.run('native:dissolve',
                          {'FIELD': [''], 'INPUT': buf2, 'SEPARATE_DISJOINT': True,
                           'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                          context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    inc = processing.run('native:addautoincrementalfield',
                         {'FIELD_NAME': 'GEN_ID', 'GROUP_FIELDS': [''], 'INPUT': dis2,
                          'MODULUS': 0, 'SORT_ASCENDING': True, 'SORT_EXPRESSION': None,
                          'SORT_NULLS_FIRST': False, 'START': 0,
                          'OUTPUT': os.path.join(folders['qgis'], 'incremented_buffer.shp')},
                         context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    # join id to points
    joined = processing.run('native:joinattributesbylocation',
                            {'DISCARD_NONMATCHING': False, 'INPUT': road_intersections_path, 'JOIN': inc,
                             'JOIN_FIELDS': ['GEN_ID'], 'METHOD': 0, 'PREDICATE': [0], 'PREFIX': None,
                             'OUTPUT': os.path.join(folders['qgis'], 'inlets_and_outlets_with_uniqueID.shp')},
                            context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    # join points → path
    p2p = processing.run('native:pointstopath',
                         {'CLOSE_PATH': False, 'GROUP_EXPRESSION': 'GEN_ID', 'INPUT': joined,
                          'NATURAL_SORT': True, 'ORDER_EXPRESSION': None,
                          'OUTPUT': os.path.join(folders['qgis'], 'points_to_path.shp')},
                         context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    # ensure downstream direction (use DEM raster_value) – DEM must be in project to evaluate, add temporarily
    QgsProject.instance().addMapLayer(dem_layer)
    geomfix = processing.run('native:geometrybyexpression',
                             {'EXPRESSION': "if(raster_value('DEM',1,start_point($geometry))"
                                            "<raster_value('DEM',1,end_point($geometry)), "
                                            "reverse($geometry),$geometry)",
                              'INPUT': p2p, 'OUTPUT_GEOMETRY': 1, 'WITH_M': False, 'WITH_Z': True,
                              'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                             context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    # refactor to TUFLOW-like schema
    out_path = os.path.join(folders['culvert'], '1d_nwk.shp')
    processing.run('native:refactorfields',
                   {'FIELDS_MAPPING': [
                       {'alias': '', 'comment': '', 'expression': 'GEN_ID', 'length': 36, 'name': 'ID', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                       {'alias': '', 'comment': '', 'expression': "'C'", 'length': 4, 'name': 'Type', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                       {'alias': '', 'comment': '', 'expression': "'F'", 'length': 1, 'name': 'Ignore', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                       {'alias': '', 'comment': '', 'expression': "'T'", 'length': 1, 'name': 'UCS', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                       {'alias': '', 'comment': '', 'expression': '$length', 'length': 15, 'name': 'Len_or_ANA', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '0.024', 'length': 15, 'name': 'n_nF_Cd', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': "raster_value('DEM', 1, start_point($geometry))", 'length': 15, 'name': 'US_Invert', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': "raster_value('DEM', 1, end_point($geometry))", 'length': 15, 'name': 'DS_Invert', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '"Form_Loss"', 'length': 15, 'name': 'Form_Loss', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '"pBlockage"', 'length': 15, 'name': 'pBlockage', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '"Inlet_Type"', 'length': 50, 'name': 'Inlet_Type', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                       {'alias': '', 'comment': '', 'expression': '"Conn_1D_2D"', 'length': 4, 'name': 'Conn_1D_2D', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                       {'alias': '', 'comment': '', 'expression': '"Conn_No"', 'length': 8, 'name': 'Conn_No', 'precision': 0, 'sub_type': 0, 'type': 2, 'type_name': 'integer'},
                       {'alias': '', 'comment': '', 'expression': '"Width_or_D"', 'length': 15, 'name': 'Width_or_D', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '"Height_or_"', 'length': 15, 'name': 'Height_or_', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '"Number_of"', 'length': 8, 'name': 'Number_of', 'precision': 0, 'sub_type': 0, 'type': 2, 'type_name': 'integer'},
                       {'alias': '', 'comment': '', 'expression': '"HConF_or_W"', 'length': 15, 'name': 'HConF_or_W', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '1.0', 'length': 15, 'name': 'WConF_or_W', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '0.5', 'length': 15, 'name': 'EntryC_or_', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                       {'alias': '', 'comment': '', 'expression': '1.0', 'length': 15, 'name': 'ExitC_or_W', 'precision': 5, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}
                   ],
                       'INPUT': geomfix,
                       'OUTPUT': out_path},
                   context=context, feedback=feedback, is_child_algorithm=True)
    return out_path

def extract_pour_points(context, feedback, folders, culvert_network_layer_or_path):
    if isinstance(culvert_network_layer_or_path, str):
        v = QgsVectorLayer(culvert_network_layer_or_path, "1d_nwk", "ogr")
    else:
        v = culvert_network_layer_or_path

    out_pp = os.path.join(folders['pcraster'], 'pour_points.shp')
    processing.run('native:extractspecificvertices',
                   {'INPUT': v, 'VERTICES': '0', 'OUTPUT': out_pp},
                   context=context, feedback=feedback, is_child_algorithm=True)
    return out_pp

# ----------------------------
# Whitebox prep & delineation
# ----------------------------
def whitebox_prepare(context, feedback, folders, dem_layer):
    dem_tif = os.path.join(folders['whitebox'], "cleaned_dem.tif")
    processing.run('gdal:translate',
                   {'COPY_SUBDATASETS': False, 'DATA_TYPE': 0, 'EXTRA': '', 'INPUT': dem_layer,
                    'NODATA': -9999, 'OPTIONS': None, 'TARGET_CRS': dem_layer.crs(), 'OUTPUT': dem_tif},
                   context=context, feedback=feedback, is_child_algorithm=True)
    wbt = WhiteboxTools()
    wbt.set_verbose_mode(True)
    dem_filled = os.path.join(folders['whitebox'], "filled_dem.tif")
    flowdir = os.path.join(folders['whitebox'], "flow_dir.tif")
    flowacc = os.path.join(folders['whitebox'], "flow_acc.tif")
    wbt.fill_depressions(dem_tif, dem_filled)
    wbt.d8_pointer(dem_filled, flowdir)
    wbt.d8_flow_accumulation(dem_filled, flowacc)
    return dem_filled, flowdir, flowacc

def add_equal_area_slope(line_layer_path: str, dem_path: str, csv_filepath: str):
    """
    Calls bundled Equal Area Slope plugin code to compute EAS and write to a CSV.
    Then writes 'EAS' attribute onto the first feature of line layer.
    """
    try:
        from .resources.Equal_area_slope_QGIS_Plugin.EA_Slope import EA_Slope
    except Exception as e:
        raise RuntimeError('Equal_area_slope_QGIS_Plugin not available') from e

    vlayer = QgsVectorLayer(line_layer_path, "stream_path", "ogr")
    rlayer = QgsRasterLayer(dem_path, "dem")
    eas = EA_Slope(None)
    eas.main(vlayer, rlayer, csv_filepath)

    eas_value = None
    with open(csv_filepath, 'r', newline='') as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
        if row and 'EAS' in row:
            eas_value = float(row['EAS'])
    if eas_value is None:
        raise RuntimeError('EAS value not found in CSV')

    vlayer.startEditing()
    if vlayer.fields().indexOf('EAS') == -1:
        vlayer.dataProvider().addAttributes([QgsField('EAS', QVariant.Double)])
        vlayer.updateFields()
    feat = next(vlayer.getFeatures(), None)
    if feat is not None:
        feat['EAS'] = eas_value
        vlayer.updateFeature(feat)
    vlayer.commitChanges()

def delineate_for_pour_points(context, feedback, folders, pour_points_path: str,
                              dem_filled_path: str, flowdir_path: str, flowacc_path: str, snap_dist: float):
    wbt = WhiteboxTools()
    wbt.set_verbose_mode(True)

    snapped_pp = os.path.join(folders['pour_points'], "snapped_pour_points.shp")
    wbt.snap_pour_points(pour_points_path, flowacc_path, snapped_pp, snap_dist)

    # split vector by 'ID' → individual pour points
    processing.run('native:splitvectorlayer',
                   {'FIELD': 'ID', 'FILE_TYPE': 1, 'INPUT': snapped_pp, 'PREFIX_FIELD': True,
                    'OUTPUT': folders['pour_points']},
                   context=context, feedback=feedback, is_child_algorithm=True)

    # For each pour point, create watershed & longest flowpath + EAS
    pp_layer = QgsVectorLayer(snapped_pp, 'pour_points', 'ogr')
    processed_ids, catchment_paths, flowpath_paths = [], [], []

    for feat in pp_layer.getFeatures():
        value = int(feat['ID'])
        processed_ids.append(value)
        pp_path = os.path.join(folders['pour_points'], f"ID_{value}.shp")
        ws_tif = os.path.join(folders['catchments'], f"catchment_{value}.tif")
        ws_shp = os.path.join(folders['catchments'], f"catchment_{value}.shp")
        flow_shp = os.path.join(folders['stream_paths'], f"longest_flowpath_{value}.shp")
        flow_csv = os.path.join(folders['stream_paths'], f"longest_flowpath_{value}.csv")

        wbt.watershed(flowdir_path, pp_path, ws_tif)
        wbt.longest_flowpath(dem_filled_path, ws_tif, flow_shp)
        add_equal_area_slope(flow_shp, dem_filled_path, flow_csv)

        # vectorize watershed & dissolve
        tempA = processing.run('gdal:polygonize',
                               {'BAND': 1, 'EIGHT_CONNECTEDNESS': False, 'EXTRA': '', 'FIELD': 'DN',
                                'INPUT': ws_tif, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                               context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
        tempB = processing.run('native:removenullgeometries',
                               {'INPUT': tempA, 'REMOVE_EMPTY': True, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
                               context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
        processing.run('native:dissolve',
                       {'FIELD': [''], 'INPUT': tempB, 'SEPARATE_DISJOINT': False, 'OUTPUT': ws_shp},
                       context=context, feedback=feedback, is_child_algorithm=True)

        catchment_paths.append(ws_shp)
        flowpath_paths.append(flow_shp)

    return processed_ids, catchment_paths, flowpath_paths

# ----------------------------
# Hydrology: flow rates
# ----------------------------
def compute_flow_rates(feedback, processed_ids: List[int], catchment_filepaths: List[str],
                       flowpath_filepaths: List[str], selected_runoff_method: int, area_factor: float) -> Dict[int, float]:

    flow_by_id: Dict[int, float] = {}
    for value in processed_ids:
        if feedback and feedback.isCanceled(): return {}

        catch_layer = QgsVectorLayer(catchment_filepaths[value], "catchment", "ogr")
        feat = next(catch_layer.getFeatures(), None)
        if feat is None:
            continue
        geom = QgsGeometry(feat.geometry())
        area_km2 = geom.area() / 1_000_000
        area_km2 = area_km2 * area_factor
        if feedback: feedback.pushInfo(f'🗺️ Area for {value} is {area_km2:.4f} km2')

        # centroid lat/long for Flavell method
        centroid = geom.centroid().asPoint()
        transform = QgsCoordinateTransform(catch_layer.sourceCrs(),
                                           QgsCoordinateReferenceSystem('EPSG:4326'),
                                           QgsProject.instance())
        lonlat = transform.transform(centroid)
        longitude, latitude = abs(float(lonlat.x())), abs(float(lonlat.y()))
        if feedback: feedback.pushInfo(f'📍 ID {value}: LAT={latitude:.6f}, LONG={longitude:.6f}')

        # flowpath attributes
        flow_layer = QgsVectorLayer(flowpath_filepaths[value], "flowpath", "ogr")
        f = next(flow_layer.getFeatures(), None)
        if f is None:
            continue
        slope_m_per_km = f['EAS'] * 10.0
        length_km = f['LENGTH'] / 1000.0

        if selected_runoff_method == 0:
            # Flavell 2012, RFFP 2000 (Q10)
            Q10 = (2.36e-34
                   * (area_km2 * (slope_m_per_km ** 0.5)) ** 0.81
                   * (latitude ** -15.24) * (longitude ** 26.28)
                   * (((length_km ** 2) / area_km2) ** -0.39)
                   )
            flow_by_id[int(value)] = Q10
        elif selected_runoff_method == 1:
            # Placeholder for Rational — not implemented here
            if feedback: feedback.pushInfo(f'🌧️ Rational Method Not Configured for ID {value}')
        else:
            if feedback: feedback.pushInfo(f'🌧️ Runoff method not recognised for ID {value}')

        if feedback:
            q = flow_by_id.get(int(value), float('nan'))
            feedback.pushInfo(f'🗺️ ID {value}: A={area_km2:.3f} km², L={length_km:.3f} km, S={slope_m_per_km:.2f} m/km → Q={q:.4f}')
    return flow_by_id

# ----------------------------
# Hydraulics: HDS-5 sizing
# ----------------------------
def size_culverts_HDS5(feedback, processed_ids: List[int], culvert_network_layer: QgsVectorLayer,
                       flow_by_id: Dict[int, float], pipe_diameters: Tuple[float, ...],
                       headwater_limit: float, mannings_n: float) -> QgsVectorLayer:
    if not culvert_network_layer.isEditable():
        culvert_network_layer.startEditing()

    # inlet constants (Thin Edge Projecting, CMP) – HY-8/HDS-5
    a, b, c, d, e, f = 0.187321, 0.56771, -0.156544, 0.0447052, -0.00343602, 8.96610e-05
    KE, SR = 0.9, 0.5

    Ku = 29.0
    n = mannings_n
    g = 9.81

    for value in processed_ids:
        if feedback and feedback.isCanceled(): return culvert_network_layer
        Q = flow_by_id.get(int(value))
        if Q is None:
            continue

        request = f"\"ID\"={value}"
        for culv in culvert_network_layer.getFeatures(request):
            L = culv['Len_or_ANA']
            us_inv = culv['US_Invert']
            ds_inv = culv['DS_Invert']
            Ls = us_inv - ds_inv

            best_ratio = -1.0
            chosen_D = -1.0

            for D in pipe_diameters:
                if feedback and feedback.isCanceled(): return culvert_network_layer
                B = D
                QBD = Q / (B * (D ** 1.5))
                Hw_ic = (a + b*QBD + c*QBD**2 + d*QBD**3 + e*QBD**4 + f*QBD**5) * D
                # outlet control
                A = math.pi * D**2 / 4.0
                P = math.pi * D
                V = Q / A
                R = A / P
                He = KE * V**2 / (2 * g)
                Hf = (Ku * (n**2) * L / (R**1.33)) * (V**2) / (2*g)
                Ho = V**2 / (2*g)
                Hl = He + Hf + Ho
                Tw = D
                Hw_oc = Tw + Hl - Ls

                # pick governing & within limit
                ratio_ic = Hw_ic / D
                ratio_oc = Hw_oc / D
                ratio = ratio_ic if Hw_ic > Hw_oc else ratio_oc
                if ratio < headwater_limit and ratio > best_ratio:
                    best_ratio = ratio
                    chosen_D = D

            culv['Width_or_D'] = float(chosen_D) if chosen_D > 0 else None
            culv['Number_of'] = int(1)  # future: multi-barrel
            culvert_network_layer.updateFeature(culv)
            if feedback:
                feedback.pushInfo(f'⭕ ID {value} → D={chosen_D} m, Hw/D={best_ratio:.3f}')

    culvert_network_layer.commitChanges()
    return culvert_network_layer