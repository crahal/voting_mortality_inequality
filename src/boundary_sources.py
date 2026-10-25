"""Restore the original ONS shapefile serialization from public ArcGIS exports.

ArcGIS now exports extra DBF fields and different numeric formatting. Geometry
is not transformed. Re-encode the original attribute schema and export metadata;
the caller must verify every resulting component against the original hashes.
"""

import struct

import geopandas as gpd


BOUNDARIES = {
    2019: {
        "stem": "WPC_Dec_2019_GCB_UK",
        "item": "11705b3f6efd4cc092580e269a86500f",
        "created": (2023, 4, 4, "13180800"),
        "fields": [
            ("pcon19cd", "C", 9, 0), ("pcon19nm", "C", 43, 0),
            ("bng_e", "N", 10, 0), ("bng_n", "N", 10, 0),
            ("long", "F", 19, 11), ("lat", "F", 19, 11),
            ("GlobalID", "C", 38, 0),
        ],
    },
    2024: {
        "stem": "PCON_JULY_2024_UK_BFC",
        "item": "0d698c9712de4afcac9377367d831c1a",
        "created": (2024, 6, 4, "13404400"),
        "fields": [
            ("PCON24CD", "C", 9, 0), ("PCON24NM", "C", 40, 0),
            ("PCON24NMW", "C", 32, 0), ("BNG_E", "N", 10, 0),
            ("BNG_N", "N", 10, 0), ("LONG", "F", 13, 11),
            ("LAT", "F", 13, 11), ("GlobalID", "C", 38, 0),
        ],
    },
}


def boundary_download_url(year):
    item = BOUNDARIES[year]["item"]
    return (f"https://hub.arcgis.com/api/v3/datasets/{item}_0/downloads/data"
            "?format=shp&spatialRefId=27700")


def encode_original_dbf(frame, year):
    """Serialize attribute values to the original Esri dBASE III schema.

The standard GIS readers handle parsing. Only writing needs this small encoder:
the original Esri F fields use scientific notation, unlike GDAL's DBF writer.
No constituency values are stored in this recipe or inferred from local inputs.
"""
    spec = BOUNDARIES[year]
    fields = spec["fields"]
    y, month, day, _ = spec["created"]
    header_length = 33 + 32 * len(fields)
    record_length = 1 + sum(field[2] for field in fields)
    payload = bytearray(struct.pack(
        "<BBBBIHH20x", 3, y - 1900, month, day, len(frame),
        header_length, record_length,
    ))
    for name, kind, width, decimals in fields:
        payload.extend(struct.pack(
            "<11sc4xBB14x", name.encode("ascii"), kind.encode("ascii"), width, decimals,
        ))
    payload.extend(b"\r")
    for row in frame.to_dict("records"):
        payload.extend(b" ")
        for name, kind, width, _ in fields:
            value = row[name]
            if name == "GlobalID":
                value = value.strip("{}").lower()
            if kind == "C":
                value = "" if value is None else str(value)
                data = value.encode("utf-8").ljust(width)
            elif kind == "N":
                if int(value) != value:
                    raise ValueError(f"Non-integer boundary attribute: {name}={value}")
                data = f"{int(value):{width}d}".encode("ascii")
            else:
                precision = 11 if width == 19 else 5
                data = f"{value:{width}.{precision}e}".encode("ascii")
            if len(data) != width:
                raise ValueError(f"Boundary attribute exceeds its original width: {name}")
            payload.extend(data)
    payload.extend(b"\x1a")
    return bytes(payload)


def original_metadata(year):
    y, month, day, time = BOUNDARIES[year]["created"]
    properties = "<DataProperties><itemProps/></DataProperties>" if year == 2019 else "<DataProperties/>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\r\n'
        '<metadata xml:lang="en"><Esri>'
        f"<CreaDate>{y:04d}{month:02d}{day:02d}</CreaDate><CreaTime>{time}</CreaTime>"
        "<ArcGISFormat>1.0</ArcGISFormat><SyncOnce>TRUE</SyncOnce>"
        f"{properties}</Esri></metadata>\r\n"
    ).encode("ascii")


def restore_boundary_attributes(directory, year):
    stem = BOUNDARIES[year]["stem"]
    frame = gpd.read_file(directory / f"{stem}.shp", ignore_geometry=True)
    (directory / f"{stem}.dbf").write_bytes(encode_original_dbf(frame, year))
    (directory / f"{stem}.shp.xml").write_bytes(original_metadata(year))
