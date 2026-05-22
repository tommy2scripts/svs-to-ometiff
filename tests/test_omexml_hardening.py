"""Exhaustive tests for OME-XML schema conformance, extreme parameter safety, and attribute escaping."""

import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import pytest

from svs_to_ometiff.writer import build_ome_xml, write_pyramidal_ometiff
from svs_to_ometiff.verify import verify_ometiff


def test_build_ome_xml_standard_formatting() -> None:
    """Test standard valid parameters produce expected elements."""
    xml_str = build_ome_xml(
        full_width=1024,
        full_height=768,
        mpp=0.25,
        image_name="StandardSlide",
        magnification=40,
    )
    
    root = ET.fromstring(xml_str)
    assert root.tag.endswith("OME")
    
    # Check pixels element
    pixels_elem = None
    for elem in root.iter():
        if elem.tag.endswith("Pixels"):
            pixels_elem = elem
            break
            
    assert pixels_elem is not None
    assert pixels_elem.get("SizeX") == "1024"
    assert pixels_elem.get("SizeY") == "768"
    assert pixels_elem.get("PhysicalSizeX") == "0.25"
    assert pixels_elem.get("PhysicalSizeY") == "0.25"
    assert pixels_elem.get("PhysicalSizeXUnit") == "um"
    assert pixels_elem.get("Type") == "uint8"
    
    # Check image elements and Name attribute
    image_elem = None
    for elem in root.iter():
        if elem.tag.endswith("Image"):
            image_elem = elem
            break
            
    assert image_elem is not None
    assert image_elem.get("Name") == "StandardSlide"
    
    # Check Instrument/Objective since magnification was provided
    obj_elem = None
    for elem in root.iter():
        if elem.tag.endswith("Objective"):
            obj_elem = elem
            break
            
    assert obj_elem is not None
    assert obj_elem.get("NominalMagnification") == "40"


def test_build_ome_xml_no_magnification() -> None:
    """Test that Instrument/Objective are omitted when magnification is absent."""
    xml_str = build_ome_xml(
        full_width=500,
        full_height=600,
        mpp=0.5,
        image_name="NoMagSlide",
        magnification=None,
    )
    
    root = ET.fromstring(xml_str)
    
    # Confirm no Instrument/Objective elements exist
    for elem in root.iter():
        assert not elem.tag.endswith("Instrument")
        assert not elem.tag.endswith("Objective")


@pytest.mark.parametrize(
    "extreme_name,expected_parsed_name",
    [
        ('Slide"With"Quotes', 'Slide"With"Quotes'),
        ("Slide'With'SingleQuotes", "Slide'With'SingleQuotes"),
        ("Slide & Another", "Slide & Another"),
        ("Slide <with> tags", "Slide <with> tags"),
        ("🔬 Slide with Emojis 🧬", "🔬 Slide with Emojis 🧬"),
        ("Slide-ü-ñ-汉字", "Slide-ü-ñ-汉字"),
        ("<script>alert('XSS')</script>", "<script>alert('XSS')</script>"),
    ],
)
def test_build_ome_xml_special_character_escaping(extreme_name: str, expected_parsed_name: str) -> None:
    """Test that special characters in image names are safely XML-escaped and correctly parsed back."""
    xml_str = build_ome_xml(
        full_width=100,
        full_height=100,
        mpp=0.5,
        image_name=extreme_name,
    )
    
    # Ensure it's valid XML by parsing it
    root = ET.fromstring(xml_str)
    
    # Find the Image element and verify Name attribute matches exactly
    image_elem = None
    for elem in root.iter():
        if elem.tag.endswith("Image"):
            image_elem = elem
            break
            
    assert image_elem is not None
    assert image_elem.get("Name") == expected_parsed_name


def test_build_ome_xml_invalid_inputs() -> None:
    """Verify that build_ome_xml raises ValueError for non-positive dimensions and MPP."""
    with pytest.raises(ValueError, match="dimensions must be positive"):
        build_ome_xml(full_width=0, full_height=100, mpp=0.5)
        
    with pytest.raises(ValueError, match="dimensions must be positive"):
        build_ome_xml(full_width=100, full_height=-10, mpp=0.5)
        
    with pytest.raises(ValueError, match="mpp must be positive"):
        build_ome_xml(full_width=100, full_height=100, mpp=0.0)
        
    with pytest.raises(ValueError, match="mpp must be positive"):
        build_ome_xml(full_width=100, full_height=100, mpp=-0.1)


def test_build_ome_xml_extreme_numeric_boundaries() -> None:
    """Verify that extreme dimensions and MPP values produce well-formed XML."""
    # Extremely large dimensions (e.g. 10 million pixels square)
    xml_str1 = build_ome_xml(
        full_width=10_000_000,
        full_height=10_000_000,
        mpp=0.25,
    )
    root1 = ET.fromstring(xml_str1)
    pixels_elem1 = next(e for e in root1.iter() if e.tag.endswith("Pixels"))
    assert pixels_elem1.get("SizeX") == "10000000"
    
    # Extremely small MPP values (e.g., nanometer range: 1e-6)
    xml_str2 = build_ome_xml(
        full_width=100,
        full_height=100,
        mpp=1e-6,
    )
    root2 = ET.fromstring(xml_str2)
    pixels_elem2 = next(e for e in root2.iter() if e.tag.endswith("Pixels"))
    assert float(pixels_elem2.get("PhysicalSizeX")) == 1e-6


def test_integration_extreme_metadata_writing_and_verification(tmp_path: Path) -> None:
    """Full pipeline integration testing extreme metadata parameter roundtrip."""
    output_path = tmp_path / "extreme.ome.tiff"
    
    # Create a tiny 1-level pyramid
    pyramid = [np.ones((64, 64, 3), dtype=np.uint8) * 128]
    
    extreme_name = "Extreme & Highly <Escaped> 'Slide' \"Name\" - 🔬"
    extreme_mpp = 0.123456
    extreme_mag = 40.5
    
    write_pyramidal_ometiff(
        output_path=str(output_path),
        pyramid=pyramid,
        mpp=extreme_mpp,
        tile_size=16,  # small tile size for testing
        compression="none",
        image_name=extreme_name,
        magnification=extreme_mag,
        verbose=False,
    )
    
    assert output_path.exists()
    
    # Verify the output file structurally and compare metadata fields
    verify_result = verify_ometiff(
        path=str(output_path),
        min_levels=1,
        expected_tile_size=16,
    )
    
    assert verify_result["pass"] is True
    assert verify_result["is_ome"] is True
    assert verify_result["is_bigtiff"] is True
    assert verify_result["tile_width"] == 16
    assert verify_result["tile_height"] == 16
    
    # Parse the actual description tag from the OME-TIFF to verify it matches
    import tifffile
    with tifffile.TiffFile(str(output_path)) as tif:
        desc = tif.pages[0].description
        assert desc is not None
        
        root = ET.fromstring(desc)
        
        # Verify Escaped Name
        image_elem = next(e for e in root.iter() if e.tag.endswith("Image"))
        assert image_elem.get("Name") == extreme_name
        
        # Verify physical sizes
        pixels_elem = next(e for e in root.iter() if e.tag.endswith("Pixels"))
        assert abs(float(pixels_elem.get("PhysicalSizeX")) - extreme_mpp) < 1e-7
        assert abs(float(pixels_elem.get("PhysicalSizeY")) - extreme_mpp) < 1e-7
        
        # Verify nominal magnification
        obj_elem = next(e for e in root.iter() if e.tag.endswith("Objective"))
        assert float(obj_elem.get("NominalMagnification")) == extreme_mag
