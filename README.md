# Culvert Designer Plugin
### Automated Generation of Rural Drainage Networks 💧

>**CulvertDesigner** is a QGIS plugin created for the engineering thesis submitted as part of a Masters of Software Engineering. The objective of this plugin is to provide an automated pipeline to take a road alignment and elevation model, and output a designed culvert network.

---

## Algorithm overview

- **Automatic Catchment Delineation and stream extraction** utilising PCRaster and WhiteboxTools  
- **Longest Flow Path & Equal-Area Slope Calculation**  
- **Rainfall run-off estimation** using Flavells RFFP2000  
- **Culvert Sizing** utilising FHWA HDS-5 based equations
- **Output of culvert network** in 1d_nwk Tuflow format, ready for further processing


---

## Dependencies


To use this plugin, it is required to first install PCRaster and WhiteboxTools.
### For MAC
It is recommended to utilise a [conda virtual environment](https://docs.conda.io/en/latest/) to achieve this on MacOS.
Please refer to [PCRaster Install Guide](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_project/install.html) and [PCRaster on conda-forge](https://anaconda.org/conda-forge/pcraster)
Along with 
[WhiteboxTools Install Guide](https://www.whiteboxgeo.com/manual/wbt_book/python_scripting/scripting.html) and [Whitebox on conda-forge](https://anaconda.org/conda-forge/whitebox)
### For Windows
It is recommended to utilise OSGeo4W to achieve this on Windows OS. 
Select PCRaster on advanced install.
Use `python -m pip install whitebox` on OSGeo4W Shell


---

## Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/blake-blake/qgis-culvert-designer.git
```

### Step 2: Move the folder to the QGIS Plugin directroy
From within QGIS: Settings → User profiles → Open active profile folder

From there, navigate to python → plugins

### Step 3: Active the plugin in QGIS
1. From within QGIS: Plugins → Manage and Install Plugins 
2. Ensure CulvertDesigner is checked ✅

---

## Usage
1. Load the following files into QGIS
    * Your project data elevation model in GeoTiff format
    * A vector that represents the batter toes of a road alignment in Esri shapefile format
2. Start the plugin
3. Select **base folder directory** for outputs
4. Select **DEM and Road**
5. Select **desired strahler order** to define major streams
6. Input approximate **road width** (used to group culvert inlets with outlets)
7. ***Optionally*** select a flow direction map from a previous run (to improve processing time)
8. **Click Run!**
9. Important files will **automatically display in the QGIS canvas**, others outputs are found in the folder directory selected in step 3.
