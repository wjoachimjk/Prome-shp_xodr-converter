


# ...existing code...

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import sys
import glob
import importlib.util
import shutil
import tempfile

app = FastAPI()

# Dynamically import 00.py as a module
spec = importlib.util.spec_from_file_location("converter", os.path.join(os.path.dirname(__file__), "00.py"))
converter = importlib.util.module_from_spec(spec)
sys.modules["converter"] = converter
spec.loader.exec_module(converter)

class FolderRequest(BaseModel):
	folder_path: str

@app.post("/convert")
def convert_shapefile(request: FolderRequest):
	folder = request.folder_path
	if not os.path.isdir(folder):
		raise HTTPException(status_code=400, detail="Folder does not exist.")
	# Find input file (.geojson or .shp)
	geojson_files = glob.glob(os.path.join(folder, '*.geojson'))
	shp_files = glob.glob(os.path.join(folder, '*.shp'))
	input_files = geojson_files + shp_files
	if not input_files:
		raise HTTPException(status_code=404, detail="No .geojson or .shp file found in the folder.")
	input_file = input_files[0]
	if len(input_files) > 1:
		msg = f"Multiple files found. Using: {os.path.basename(input_file)}"
	else:
		msg = f"Using: {os.path.basename(input_file)}"
	output_xodr = os.path.join(folder, "output.xodr")
	segments, crs_wkt, crs_epsg, err = converter.read_points_from_shapefile(input_file)
	if err:
		raise HTTPException(status_code=500, detail=f"Error: {err}")
	bounds = converter.calculate_bounding_box(segments)
	converter.write_opendrive_file(segments, bounds, crs_wkt, crs_epsg, output_xodr)
	return {"message": f"Conversion complete! {msg}", "output_file": output_xodr}


@app.post("/upload_convert")
async def upload_and_convert(file: UploadFile = File(...)):
    # Only accept .shp or .geojson
    if not (file.filename.endswith('.shp') or file.filename.endswith('.geojson')):
        raise HTTPException(status_code=400, detail="Only .shp or .geojson files are supported.")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        # Run conversion
        segments, crs_wkt, crs_epsg, err = converter.read_points_from_shapefile(file_path)
        if err:
            raise HTTPException(status_code=500, detail=f"Error: {err}")
        bounds = converter.calculate_bounding_box(segments)
        output_xodr = os.path.join(tmpdir, "output.xodr")
        converter.write_opendrive_file(segments, bounds, crs_wkt, crs_epsg, output_xodr)
        return FileResponse(output_xodr, media_type="application/xml", filename="output.xodr")
# FastAPI app to convert shapefile/geojson to .xodr using logic from 00.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import sys
import glob
import importlib.util

app = FastAPI()

# Dynamically import 00.py as a module
spec = importlib.util.spec_from_file_location("converter", os.path.join(os.path.dirname(__file__), "00.py"))
converter = importlib.util.module_from_spec(spec)
sys.modules["converter"] = converter
spec.loader.exec_module(converter)

class FolderRequest(BaseModel):
	folder_path: str

@app.post("/convert")
def convert_shapefile(request: FolderRequest):
	folder = request.folder_path
	if not os.path.isdir(folder):
		raise HTTPException(status_code=400, detail="Folder does not exist.")
	# Find input file (.geojson or .shp)
	geojson_files = glob.glob(os.path.join(folder, '*.geojson'))
	shp_files = glob.glob(os.path.join(folder, '*.shp'))
	input_files = geojson_files + shp_files
	if not input_files:
		raise HTTPException(status_code=404, detail="No .geojson or .shp file found in the folder.")
	input_file = input_files[0]
	if len(input_files) > 1:
		msg = f"Multiple files found. Using: {os.path.basename(input_file)}"
	else:
		msg = f"Using: {os.path.basename(input_file)}"
	output_xodr = os.path.join(folder, "output.xodr")
	segments, crs_wkt, crs_epsg, err = converter.read_points_from_shapefile(input_file)
	if err:
		raise HTTPException(status_code=500, detail=f"Error: {err}")
	bounds = converter.calculate_bounding_box(segments)
	converter.write_opendrive_file(segments, bounds, crs_wkt, crs_epsg, output_xodr)
	return {"message": f"Conversion complete! {msg}", "output_file": output_xodr}
