"""
QS Parser Service
Extracts structured data from construction PDF drawings
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

app = FastAPI(
    title="QS Parser Service",
    description="Extract floor plan data from PDF drawings",
    version="1.0.0"
)

# CORS for main app to call this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response Models
class Point(BaseModel):
    x: float
    y: float


class Wall(BaseModel):
    start: Point
    end: Point
    length: float  # in millimeters


class Room(BaseModel):
    name: Optional[str] = None
    vertices: List[Point]
    area: float  # in square meters
    perimeter: float  # in meters


class Dimension(BaseModel):
    value: str  # Raw text like "4500mm" or "4.5m"
    numeric_value: Optional[float] = None  # Parsed to mm
    position: Point


class Door(BaseModel):
    position: Point
    width: Optional[float] = None


class Window(BaseModel):
    position: Point
    width: Optional[float] = None


class ExtractedFloorPlan(BaseModel):
    walls: List[Wall] = []
    rooms: List[Room] = []
    dimensions: List[Dimension] = []
    doors: List[Door] = []
    windows: List[Window] = []
    page_width: float
    page_height: float
    scale_factor: Optional[float] = None  # If we can detect it
    raw_text: List[str] = []  # All text found
    extraction_confidence: float  # 0-1


class HealthResponse(BaseModel):
    status: str
    version: str
    pymupdf_version: str


class ParseResponse(BaseModel):
    success: bool
    data: Optional[ExtractedFloorPlan] = None
    error: Optional[str] = None
    pages_processed: int = 0


# Routes
@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    import fitz
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        pymupdf_version=fitz.version[0]
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Alias for health check"""
    return await health_check()


@app.post("/parse", response_model=ParseResponse)
async def parse_pdf(file: UploadFile = File(...)):
    """
    Parse a PDF floor plan and extract structured data.

    Accepts: PDF file (CAD-generated preferred)
    Returns: Structured floor plan data (walls, rooms, dimensions)
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )

    try:
        # Read file content
        content = await file.read()

        # Import and use extraction service
        from app.services.pdf_extractor import extract_floor_plan

        result = extract_floor_plan(content)

        return ParseResponse(
            success=True,
            data=result,
            pages_processed=1
        )

    except Exception as e:
        return ParseResponse(
            success=False,
            error=str(e),
            pages_processed=0
        )


@app.post("/parse/multi", response_model=List[ParseResponse])
async def parse_multi_page_pdf(file: UploadFile = File(...)):
    """
    Parse a multi-page PDF and extract data from each page.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )

    try:
        content = await file.read()

        from app.services.pdf_extractor import extract_all_pages

        results = extract_all_pages(content)

        return [
            ParseResponse(success=True, data=r, pages_processed=1)
            for r in results
        ]

    except Exception as e:
        return [ParseResponse(success=False, error=str(e), pages_processed=0)]


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
