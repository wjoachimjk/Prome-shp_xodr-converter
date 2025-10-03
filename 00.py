#!/usr/bin/env python3
"""
Modified Shapefile/GeoJSON to OpenDRIVE Converter
Uses fixed projection from provided .xodr file and sets all z-coordinates to 0.
Converts to OpenDRIVE (.xodr) for RoadRunner.
"""

import math
import os
import sys
import glob
import re
from datetime import datetime

try:
    import fiona
    from pyproj import CRS, Transformer
    from lxml.etree import CDATA, Element as LxmlElement, SubElement as LxmlSubElement, tostring as lxml_tostring
except ImportError as e:
    print(f"Error: Missing dependency - {e.name}")
    print("Install with: pip install fiona pyproj lxml")
    sys.exit(1)


def read_points_from_shapefile(input_file):
    """
    Reads geometry from Shapefile/GeoJSON, auto-detects CRS,
    reprojects to fixed custom TM, sets all z to 0.
    Returns segments, target_wkt, target_epsg, error_message
    """
    segments = []
    error_message = None
    all_lons, all_lats = [], []  # For detection

    # Fixed projection from provided .xodr
    fixed_lat_0 = 1.52211268895686
    fixed_lon_0 = 33.4567869401696
    custom_proj4 = f"+proj=tmerc +lat_0={fixed_lat_0} +lon_0={fixed_lon_0} +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +vunits=m +no_defs"
    target_crs = CRS.from_proj4(custom_proj4)
    print(f"Using fixed custom TM from .xodr: {custom_proj4}")

    try:
        with fiona.open(input_file, "r") as src:
            # Extract CRS
            src_crs = src.crs
            source_crs = None
            if src_crs:
                source_crs = CRS(src_crs)
                print(f"Detected source CRS: {source_crs.name}")
            else:
                print("No CRS found. Auto-detecting...")

            # Collect coordinates, force z=0
            temp_segments = []
            for feature in src:
                geom = feature["geometry"]
                if geom["type"] == "LineString":
                    segment = []
                    for coord in geom["coordinates"]:
                        x, y = coord[0], coord[1]
                        z = 0.0  # Force z to 0
                        all_lons.append(x)
                        all_lats.append(y)
                        segment.append({'x': x, 'y': y, 'z': z})
                    if segment:
                        temp_segments.append(segment)
                elif geom["type"] == "Point":
                    x, y = geom["coordinates"][:2]
                    z = 0.0  # Force z to 0
                    all_lons.append(x)
                    all_lats.append(y)
                    temp_segments.append([{'x': x, 'y': y, 'z': z}])
                else:
                    print(f"Skipping unsupported geometry: {geom['type']}")

            if not all_lons:
                raise ValueError("No coordinates found in file.")

            # Auto-detect CRS if none
            max_abs = max(max(abs(min(all_lons)), abs(max(all_lons))), max(abs(min(all_lats)), abs(max(all_lats))))
            if source_crs is None:
                if max_abs < 180:
                    source_crs = CRS.from_epsg(4326)
                    print("Coordinates look geographic; assuming WGS84 (EPSG:4326).")
                else:
                    source_crs = CRS.from_epsg(32636)
                    print("Coordinates look projected; assuming UTM Zone 36N (EPSG:32636).")

            # Create transformer: source to target
            transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

            # Reproject segments
            for segment in temp_segments:
                reproj_segment = []
                for p in segment:
                    x, y = transformer.transform(p['x'], p['y'])
                    reproj_segment.append({'x': x, 'y': y, 'z': 0.0, 'vertex_index': 0})  # Ensure z=0
                segments.append(reproj_segment)

            target_wkt = target_crs.to_wkt()
            target_epsg = None  # Custom; no EPSG

    except Exception as e:
        error_message = f"Error processing file: {str(e)}"

    if not segments:
        error_message = error_message or "No valid geometry found."

    return segments, target_wkt, target_epsg, error_message


def calculate_geometry(points):
    road_points = []
    current_s = 0.0
    if len(points) < 2:
        return road_points
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        dx = p2['x'] - p1['x']
        dy = p2['y'] - p1['y']
        segment_length = math.sqrt(dx**2 + dy**2)
        hdg = math.atan2(dy, dx)
        road_points.append({
            's': current_s,
            'x': p1['x'],
            'y': p1['y'],
            'z': 0.0,  # Force z to 0
            'hdg': hdg,
            'length': segment_length
        })
        current_s += segment_length
    road_points.append({
        's': current_s,
        'x': points[-1]['x'],
        'y': points[-1]['y'],
        'z': 0.0,  # Force z to 0
        'hdg': road_points[-1]['hdg'] if road_points else 0.0,
        'length': 0.0
    })
    return road_points


def calculate_bounding_box(all_segments):
    all_points = [p for segment in all_segments for p in segment]
    if not all_points:
        return {'north': 0, 'south': 0, 'east': 0, 'west': 0}
    xs = [p['x'] for p in all_points]
    ys = [p['y'] for p in all_points]
    return {
        'north': max(ys),
        'south': min(ys),
        'east': max(xs),
        'west': min(xs)
    }


def write_opendrive_file(all_points_segments, bounds, crs_wkt, crs_epsg, output_file):
    root = LxmlElement("OpenDRIVE")
    geo_ref = crs_wkt if crs_wkt else '+proj=latlong +datum=WGS84'
    header = LxmlSubElement(root, "header", {
        "revMajor": "1",
        "revMinor": "4",
        "name": "Generated Road",
        "version": "1.00",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "north": f"{bounds['north']:.16f}",
        "south": f"{bounds['south']:.16f}",
        "east": f"{bounds['east']:.16f}",
        "west": f"{bounds['west']:.16f}",
        "vendor": "RoadRunner"
    })
    geoReference = LxmlSubElement(header, "geoReference")
    geoReference.text = CDATA(geo_ref)
    print(f"Using geoReference: {geo_ref[:100]}...")  # Truncated for log

    for idx, segment in enumerate(all_points_segments, 1):
        if len(segment) < 2:
            continue
        road_geometry = calculate_geometry(segment)
        road_length = sum(p['length'] for p in road_geometry)
        road = LxmlSubElement(root, "road", {
            "name": f"Road_{idx}",
            "length": f"{road_length:.16f}",
            "id": str(idx),
            "junction": "-1"
        })
        planView = LxmlSubElement(road, "planView")
        for p in road_geometry:
            geometry = LxmlSubElement(planView, "geometry", {
                "s": f"{p['s']:.16f}",
                "x": f"{p['x']:.16f}",
                "y": f"{p['y']:.16f}",
                "hdg": f"{p['hdg']:.16f}",
                "length": f"{p['length']:.16f}"
            })
            LxmlSubElement(geometry, "line")
        elevationProfile = LxmlSubElement(road, "elevationProfile")
        current_s_elev = 0.0
        for i in range(1, len(segment)):
            prev_p = segment[i - 1]
            p = segment[i]
            dist = math.sqrt((p['x'] - prev_p['x'])**2 + (p['y'] - prev_p['y'])**2)
            current_s_elev += dist
            LxmlSubElement(elevationProfile, "elevation", {
                "s": f"{current_s_elev:.16f}",
                "a": "0.0",  # Force z to 0 in elevation profile
                "b": "0.0",
                "c": "0.0",
                "d": "0.0"
            })
        lanes = LxmlSubElement(road, "lanes")
        LxmlSubElement(lanes, "laneOffset", {"s": "0.0", "a": "0.0", "b": "0.0", "c": "0.0", "d": "0.0"})
        laneSection = LxmlSubElement(lanes, "laneSection", {"s": "0.0", "singleSide": "false"})
        left = LxmlSubElement(laneSection, "left")
        LxmlSubElement(left, "lane", {"id": "1", "type": "driving", "level": "false"})
        center = LxmlSubElement(laneSection, "center")
        LxmlSubElement(center, "lane", {"id": "0", "type": "none", "level": "false"})
        right = LxmlSubElement(laneSection, "right")
        LxmlSubElement(right, "lane", {"id": "-1", "type": "driving", "level": "false"})

    xml_str = lxml_tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode('utf-8')
    with open(output_file, "w", encoding='utf-8') as f:
        f.write(xml_str)
    print(f"OpenDRIVE file generated: {output_file}")


def main():
    print("GeoJSON/Shapefile to OpenDRIVE Converter (Fixed Projection, Z=0)")
    print("=" * 60)

    # Find input file (.geojson or .shp)
    input_files = glob.glob('*.geojson') + glob.glob('*.shp')
    if not input_files:
        print("Error: No .geojson or .shp found.")
        sys.exit(1)
    input_file = input_files[0]
    if len(input_files) > 1:
        print(f"Warning: Multiple files found. Using: {input_file}")
    output_xodr = "output.xodr"

    print(f"Input: {input_file}")
    print(f"Output: {output_xodr}")

    segments, crs_wkt, crs_epsg, err = read_points_from_shapefile(input_file)
    if err:
        print(f"Error: {err}")
        sys.exit(1)

    print(f"Segments: {len(segments)}")
    print(f"Points: {sum(len(s) for s in segments)}")

    bounds = calculate_bounding_box(segments)
    print(f"Reprojected bounds: {bounds}")

    write_opendrive_file(segments, bounds, crs_wkt, crs_epsg, output_xodr)
    print("\nConversion complete! Output .xodr uses fixed projection and z=0 for all points.")


if __name__ == "__main__":
    main()