"""
PDF Floor Plan Extractor
Uses PyMuPDF to extract vector graphics and text from CAD-generated PDFs
"""

import fitz  # PyMuPDF
from typing import List, Tuple, Optional
import re
import math


def extract_floor_plan(pdf_content: bytes) -> dict:
    """
    Extract floor plan data from PDF content.

    Args:
        pdf_content: Raw PDF file bytes

    Returns:
        ExtractedFloorPlan dict with walls, rooms, dimensions, etc.
    """
    doc = fitz.open(stream=pdf_content, filetype="pdf")

    if doc.page_count == 0:
        raise ValueError("PDF has no pages")

    page = doc[0]

    # Get page dimensions
    page_width = page.rect.width
    page_height = page.rect.height

    # Extract all components using enhanced extractors
    walls = extract_walls_enhanced(page)
    dimensions = extract_dimensions(page)
    raw_text = extract_all_text(page)
    rooms = extract_rooms(page, walls)
    doors = extract_doors(page)
    windows = extract_windows(page)

    # Detect scale
    scale = detect_scale(dimensions, raw_text)

    # Calculate confidence using enhanced method
    confidence = calculate_confidence_enhanced(
        walls, dimensions, raw_text, rooms, doors, windows
    )

    doc.close()

    return {
        "walls": walls,
        "rooms": rooms,
        "dimensions": dimensions,
        "doors": doors,
        "windows": windows,
        "page_width": page_width,
        "page_height": page_height,
        "scale_factor": scale,
        "raw_text": raw_text,
        "extraction_confidence": confidence,
        "confidence": confidence  # Alias for compatibility
    }


def extract_all_pages(pdf_content: bytes) -> List[dict]:
    """Extract floor plan data from all pages of a PDF."""
    doc = fitz.open(stream=pdf_content, filetype="pdf")
    results = []

    for page_num in range(doc.page_count):
        page = doc[page_num]

        walls = extract_walls(page)
        dimensions = extract_dimensions(page)
        raw_text = extract_all_text(page)
        confidence = calculate_confidence(walls, dimensions, raw_text)

        results.append({
            "walls": walls,
            "rooms": [],
            "dimensions": dimensions,
            "doors": [],
            "windows": [],
            "page_width": page.rect.width,
            "page_height": page.rect.height,
            "scale_factor": detect_scale(dimensions, raw_text),
            "raw_text": raw_text,
            "extraction_confidence": confidence
        })

    doc.close()
    return results


def extract_walls(page: fitz.Page) -> List[dict]:
    """
    Extract wall lines from the page.

    Walls in CAD drawings are typically:
    - Thick lines (stroke width > 0.5)
    - On specific layers
    - Forming closed or connected shapes
    """
    walls = []

    # Get all drawings (vector graphics)
    drawings = page.get_drawings()

    for path in drawings:
        # Check line width - walls are usually thicker
        width = path.get("width", 0)

        for item in path.get("items", []):
            # 'l' = line, 're' = rectangle, 'c' = curve, 'qu' = quad
            if item[0] == "l":  # Line
                start = item[1]  # Point (x, y)
                end = item[2]    # Point (x, y)

                # Calculate length
                length = math.sqrt(
                    (end.x - start.x) ** 2 +
                    (end.y - start.y) ** 2
                )

                # Filter: walls are typically longer than 10 points
                # and have some thickness
                if length > 10 and width >= 0.3:
                    walls.append({
                        "start": {"x": start.x, "y": start.y},
                        "end": {"x": end.x, "y": end.y},
                        "length": length
                    })

            elif item[0] == "re":  # Rectangle (could be a thick wall)
                rect = item[1]
                # Rectangles with small width or height might be walls
                w = rect.width
                h = rect.height

                if w > 10 or h > 10:  # Meaningful size
                    # Add as 4 walls
                    walls.extend([
                        {
                            "start": {"x": rect.x0, "y": rect.y0},
                            "end": {"x": rect.x1, "y": rect.y0},
                            "length": w
                        },
                        {
                            "start": {"x": rect.x1, "y": rect.y0},
                            "end": {"x": rect.x1, "y": rect.y1},
                            "length": h
                        },
                        {
                            "start": {"x": rect.x1, "y": rect.y1},
                            "end": {"x": rect.x0, "y": rect.y1},
                            "length": w
                        },
                        {
                            "start": {"x": rect.x0, "y": rect.y1},
                            "end": {"x": rect.x0, "y": rect.y0},
                            "length": h
                        }
                    ])

    return walls


def extract_dimensions(page: fitz.Page) -> List[dict]:
    """
    Extract dimension annotations from the page.

    Looks for text matching patterns like:
    - 4500mm, 4500 mm
    - 4.5m, 4.5 m
    - 4500 (bare numbers near dimension lines)
    - 4'-6" (imperial)
    """
    dimensions = []

    # Get text with positions
    text_dict = page.get_text("dict")

    # Dimension patterns
    patterns = [
        r'(\d+(?:\.\d+)?)\s*mm',      # 4500mm, 4500 mm
        r'(\d+(?:\.\d+)?)\s*m(?!\w)',  # 4.5m but not "mm"
        r'(\d+(?:\.\d+)?)\s*cm',       # 450cm
        r"(\d+)'[\s-]?(\d+)\"?",       # 4'-6" imperial
        r'(\d{3,5})(?:\s|$)',          # Bare 4-5 digit numbers (likely mm)
    ]

    for block in text_dict.get("blocks", []):
        if "lines" not in block:
            continue

        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                bbox = span["bbox"]  # (x0, y0, x1, y1)

                # Try each pattern
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        # Calculate numeric value in mm
                        numeric = parse_dimension_to_mm(text, match)

                        dimensions.append({
                            "value": text,
                            "numeric_value": numeric,
                            "position": {
                                "x": (bbox[0] + bbox[2]) / 2,
                                "y": (bbox[1] + bbox[3]) / 2
                            }
                        })
                        break  # Only match once per span

    return dimensions


def parse_dimension_to_mm(text: str, match: re.Match) -> Optional[float]:
    """Convert dimension text to millimeters."""
    try:
        text_lower = text.lower()

        if 'mm' in text_lower:
            return float(match.group(1))
        elif 'cm' in text_lower:
            return float(match.group(1)) * 10
        elif 'm' in text_lower and 'mm' not in text_lower:
            return float(match.group(1)) * 1000
        elif "'" in text or '"' in text:
            # Imperial: feet and inches
            feet = float(match.group(1))
            inches = float(match.group(2)) if match.lastindex >= 2 else 0
            return (feet * 12 + inches) * 25.4
        else:
            # Bare number - assume mm if 3+ digits
            num = float(match.group(1))
            if num >= 100:
                return num  # Likely mm
            else:
                return num * 1000  # Likely meters
    except:
        return None


def extract_all_text(page: fitz.Page) -> List[str]:
    """Extract all text from the page."""
    text = page.get_text("text")
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return lines


def detect_scale(dimensions: List[dict], raw_text: List[str]) -> Optional[float]:
    """
    Try to detect the drawing scale.

    Looks for:
    - "Scale 1:100" or "1:50" annotations
    - Standard architectural scales
    """
    scale_pattern = r'(?:scale\s*)?1\s*:\s*(\d+)'

    for text in raw_text:
        match = re.search(scale_pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))

    return None


def calculate_confidence(
    walls: List[dict],
    dimensions: List[dict],
    raw_text: List[str]
) -> float:
    """
    Calculate confidence score for the extraction.

    Higher confidence when:
    - Many walls detected
    - Dimensions found
    - Scale detected
    - Text found
    """
    score = 0.0

    # Walls: up to 0.4
    if len(walls) > 50:
        score += 0.4
    elif len(walls) > 20:
        score += 0.3
    elif len(walls) > 5:
        score += 0.2
    elif len(walls) > 0:
        score += 0.1

    # Dimensions: up to 0.3
    if len(dimensions) > 10:
        score += 0.3
    elif len(dimensions) > 5:
        score += 0.2
    elif len(dimensions) > 0:
        score += 0.1

    # Text: up to 0.2
    if len(raw_text) > 20:
        score += 0.2
    elif len(raw_text) > 5:
        score += 0.1

    # Scale detected: 0.1
    # (checked separately since we'd need to pass it in)

    return min(score, 1.0)


# ============================================
# ENHANCED EXTRACTION FUNCTIONS (Phase 2)
# ============================================

def extract_walls_enhanced(page: fitz.Page) -> List[dict]:
    """
    Enhanced wall extraction with filtering and grouping.

    Improvements:
    - Filter by line thickness
    - Group parallel lines (double-line walls)
    - Detect wall intersections
    - Calculate actual wall thickness
    """
    walls = []
    all_lines = []

    drawings = page.get_drawings()

    # First pass: collect all lines
    for path in drawings:
        width = path.get("width", 0)
        color = path.get("color", None)

        for item in path.get("items", []):
            if item[0] == "l":
                start = item[1]
                end = item[2]

                length = math.sqrt(
                    (end.x - start.x) ** 2 +
                    (end.y - start.y) ** 2
                )

                # Calculate angle
                angle = math.atan2(end.y - start.y, end.x - start.x)

                all_lines.append({
                    "start": {"x": start.x, "y": start.y},
                    "end": {"x": end.x, "y": end.y},
                    "length": length,
                    "width": width,
                    "angle": angle,
                    "color": color
                })

    # Second pass: filter likely walls
    # Walls are typically:
    # - Longer than 20 points
    # - Horizontal or vertical (angles near 0, 90, 180, 270)
    # - Thicker lines (width > 0.3)

    for line in all_lines:
        length = line["length"]
        angle_deg = abs(math.degrees(line["angle"])) % 180
        width = line["width"]

        # Check if roughly horizontal or vertical
        is_orthogonal = (
            angle_deg < 5 or
            abs(angle_deg - 90) < 5 or
            abs(angle_deg - 180) < 5
        )

        # Wall criteria
        if length > 20 and (width >= 0.3 or is_orthogonal):
            walls.append({
                "start": line["start"],
                "end": line["end"],
                "length": length,
                "thickness": width,
                "is_orthogonal": is_orthogonal
            })

    # Third pass: merge parallel close lines (double-line walls)
    walls = merge_parallel_walls(walls)

    return walls


def merge_parallel_walls(walls: List[dict], tolerance: float = 15.0) -> List[dict]:
    """
    Merge parallel walls that are close together.
    In CAD, walls are often drawn as two parallel lines.
    """
    if len(walls) < 2:
        return walls

    merged = []
    used = set()

    for i, wall1 in enumerate(walls):
        if i in used:
            continue

        # Find parallel nearby walls
        for j, wall2 in enumerate(walls[i+1:], i+1):
            if j in used:
                continue

            # Check if parallel (same angle)
            # Check if close (perpendicular distance < tolerance)
            if are_walls_parallel_and_close(wall1, wall2, tolerance):
                # Merge: use midpoint line
                merged_wall = merge_two_walls(wall1, wall2)
                merged.append(merged_wall)
                used.add(i)
                used.add(j)
                break

        if i not in used:
            merged.append(wall1)

    return merged


def are_walls_parallel_and_close(w1: dict, w2: dict, tolerance: float) -> bool:
    """Check if two walls are parallel and close together."""
    # Simplified check: compare midpoints
    mid1_x = (w1["start"]["x"] + w1["end"]["x"]) / 2
    mid1_y = (w1["start"]["y"] + w1["end"]["y"]) / 2
    mid2_x = (w2["start"]["x"] + w2["end"]["x"]) / 2
    mid2_y = (w2["start"]["y"] + w2["end"]["y"]) / 2

    distance = math.sqrt((mid2_x - mid1_x)**2 + (mid2_y - mid1_y)**2)

    # Similar length check
    length_diff = abs(w1["length"] - w2["length"])

    return distance < tolerance and length_diff < w1["length"] * 0.2


def merge_two_walls(w1: dict, w2: dict) -> dict:
    """Create a single wall from two parallel walls."""
    return {
        "start": {
            "x": (w1["start"]["x"] + w2["start"]["x"]) / 2,
            "y": (w1["start"]["y"] + w2["start"]["y"]) / 2
        },
        "end": {
            "x": (w1["end"]["x"] + w2["end"]["x"]) / 2,
            "y": (w1["end"]["y"] + w2["end"]["y"]) / 2
        },
        "length": (w1["length"] + w2["length"]) / 2,
        "thickness": abs(
            math.sqrt(
                (w1["start"]["x"] - w2["start"]["x"])**2 +
                (w1["start"]["y"] - w2["start"]["y"])**2
            )
        )
    }


def extract_rooms(page: fitz.Page, walls: List[dict]) -> List[dict]:
    """
    Detect rooms from walls and text labels.

    Strategy:
    1. Find closed polygons from walls
    2. Match room labels (text) to polygons
    3. Calculate area and perimeter
    """
    rooms = []

    # Get all text that might be room labels
    room_labels = extract_room_labels(page)

    # For now, use simple approach:
    # Find text that looks like room names and their positions
    for label in room_labels:
        rooms.append({
            "name": label["text"],
            "label": label["text"],  # Alias for compatibility
            "vertices": [],  # Would need polygon detection
            "area": 0,  # Would calculate from vertices
            "perimeter": 0,
            "label_position": label["position"]
        })

    return rooms


def extract_room_labels(page: fitz.Page) -> List[dict]:
    """
    Extract text that looks like room names.

    Common room names:
    - Kitchen, Bedroom, Bathroom, Living Room, etc.
    - Or abbreviations: KIT, BED, BTH, LIV
    - Or numbered: Bedroom 1, WC 2
    """
    labels = []

    room_keywords = [
        'kitchen', 'bedroom', 'bathroom', 'living', 'dining',
        'hall', 'hallway', 'corridor', 'utility', 'storage',
        'garage', 'office', 'study', 'en-suite', 'ensuite',
        'wc', 'toilet', 'shower', 'bath', 'lounge', 'sitting',
        'family', 'breakfast', 'pantry', 'laundry', 'closet',
        'wardrobe', 'landing', 'stairs', 'porch', 'entrance',
        'reception', 'drawing', 'master', 'guest', 'kids',
        'kit', 'bed', 'bth', 'liv', 'din'  # Abbreviations
    ]

    text_dict = page.get_text("dict")

    for block in text_dict.get("blocks", []):
        if "lines" not in block:
            continue

        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                text_lower = text.lower()
                bbox = span["bbox"]

                # Check if contains room keyword
                for keyword in room_keywords:
                    if keyword in text_lower:
                        labels.append({
                            "text": text,
                            "position": {
                                "x": (bbox[0] + bbox[2]) / 2,
                                "y": (bbox[1] + bbox[3]) / 2
                            }
                        })
                        break

    return labels


def extract_doors(page: fitz.Page) -> List[dict]:
    """
    Detect doors in floor plans.

    Doors are typically represented as:
    - Arc (swing direction)
    - Gap in wall with perpendicular line
    - Specific symbols/blocks
    """
    doors = []

    drawings = page.get_drawings()

    for path in drawings:
        for item in path.get("items", []):
            # Look for arcs (door swings)
            if item[0] == "c":  # Curve/arc
                # item format: ("c", point1, point2, point3, point4)
                # This is a cubic Bezier curve
                points = item[1:]

                # Calculate approximate center
                if len(points) >= 2:
                    center_x = sum(p.x for p in points) / len(points)
                    center_y = sum(p.y for p in points) / len(points)

                    # Arcs with radius roughly 600-900mm are likely doors
                    # (standard door widths)
                    doors.append({
                        "position": {"x": center_x, "y": center_y},
                        "width": None,  # Would need more analysis
                        "type": "swing"
                    })

    return doors


def extract_windows(page: fitz.Page) -> List[dict]:
    """
    Detect windows in floor plans.

    Windows are typically:
    - Double parallel lines (thinner than walls)
    - Specific symbols
    - Gaps in external walls with glass indication
    """
    windows = []

    # For now, look for specific patterns in drawings
    # This would need refinement based on actual CAD conventions

    drawings = page.get_drawings()

    for path in drawings:
        width = path.get("width", 0)

        # Windows are often drawn with thinner lines
        if 0.1 < width < 0.3:
            for item in path.get("items", []):
                if item[0] == "re":  # Rectangle
                    rect = item[1]
                    # Small rectangles might be window symbols
                    if rect.width < 50 and rect.height < 50:
                        windows.append({
                            "position": {
                                "x": (rect.x0 + rect.x1) / 2,
                                "y": (rect.y0 + rect.y1) / 2
                            },
                            "width": max(rect.width, rect.height)
                        })

    return windows


def calculate_confidence_enhanced(
    walls: List[dict],
    dimensions: List[dict],
    raw_text: List[str],
    rooms: List[dict],
    doors: List[dict],
    windows: List[dict]
) -> float:
    """Enhanced confidence calculation."""
    score = 0.0

    # Walls: up to 0.3
    if len(walls) > 30:
        score += 0.3
    elif len(walls) > 15:
        score += 0.2
    elif len(walls) > 5:
        score += 0.1

    # Dimensions: up to 0.25
    if len(dimensions) > 10:
        score += 0.25
    elif len(dimensions) > 5:
        score += 0.15
    elif len(dimensions) > 0:
        score += 0.05

    # Rooms: up to 0.2
    if len(rooms) > 5:
        score += 0.2
    elif len(rooms) > 2:
        score += 0.1
    elif len(rooms) > 0:
        score += 0.05

    # Doors/windows: up to 0.15
    if len(doors) > 3 or len(windows) > 3:
        score += 0.15
    elif len(doors) > 0 or len(windows) > 0:
        score += 0.05

    # Text: up to 0.1
    if len(raw_text) > 10:
        score += 0.1
    elif len(raw_text) > 0:
        score += 0.05

    return min(score, 1.0)
