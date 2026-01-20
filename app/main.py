"""
QS Parser API - Floor plan extraction service.
Supports PDF (with OCR fallback) and DXF files.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import os
from typing import Dict, Any

from app.services.pdf_extractor import extract_from_pdf
from app.services.dxf_extractor import extract_from_dxf

app = FastAPI(
    title="QS Parser",
    description="Extract floor plan data from PDF and DXF files",
    version="2.0.0"
)

# CORS for main app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "service": "QS Parser",
        "version": "2.0.0",
        "supported_formats": ["pdf", "dxf"],
        "features": ["ocr_fallback", "dxf_parsing"]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = {
        "status": "healthy",
        "pdf_parser": "ok",
        "dxf_parser": "ok",
        "ocr_available": False
    }

    # Check OCR availability
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        health_status["ocr_available"] = True
    except Exception:
        health_status["ocr_available"] = False

    return health_status


@app.post("/parse")
async def parse_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Parse a floor plan file (PDF or DXF).
    Returns extracted walls, rooms, dimensions, doors, windows.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Get file extension
    ext = file.filename.lower().split('.')[-1]

    if ext not in ['pdf', 'dxf']:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: pdf, dxf"
        )

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Extract based on file type
        if ext == 'pdf':
            result = extract_from_pdf(tmp_path)
        elif ext == 'dxf':
            result = extract_from_dxf(tmp_path)

        result['filename'] = file.filename
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/parse/multi")
async def parse_multi_page(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Parse a multi-page PDF, returning data for each page.
    For DXF files, behaves the same as /parse.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.lower().split('.')[-1]

    if ext not in ['pdf', 'dxf']:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: pdf, dxf"
        )

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if ext == 'dxf':
            # DXF doesn't have pages
            result = extract_from_dxf(tmp_path)
            result['filename'] = file.filename
            return result

        # Multi-page PDF processing
        import fitz
        doc = fitz.open(tmp_path)
        pages_data = []

        for page_num in range(len(doc)):
            # Create temp file for single page
            single_page_doc = fitz.open()
            single_page_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as page_tmp:
                single_page_doc.save(page_tmp.name)
                single_page_doc.close()

                page_result = extract_from_pdf(page_tmp.name)
                page_result['page_number'] = page_num + 1
                pages_data.append(page_result)

                os.unlink(page_tmp.name)

        doc.close()

        # Combine results
        combined = {
            'filename': file.filename,
            'total_pages': len(pages_data),
            'pages': pages_data,
            'summary': {
                'total_walls': sum(len(p['walls']) for p in pages_data),
                'total_dimensions': sum(len(p['dimensions']) for p in pages_data),
                'total_rooms': sum(len(p['rooms']) for p in pages_data),
                'ocr_used_on_pages': [p['page_number'] for p in pages_data if p.get('ocr_used', False)]
            }
        }

        return combined

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
