from setuptools import setup, find_packages

setup(
    name="realtor_doc_processor",
    version="0.2.0",
    description="Classify, split, and rename real estate transaction documents using a cloud LLM.",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.27.0",
        "pypdf>=4.0.0",
        "pdfplumber>=0.10.0",
        "reportlab>=4.0.0",
    ],
    extras_require={
        # Only needed for scanned/image PDFs (OCR) and vision models.
        "ocr": ["pdf2image>=1.17.0", "Pillow>=10.0.0", "pytesseract>=0.3.10"],
        "web": ["flask>=3.0.0", "gunicorn>=21.0.0"],
    },
    entry_points={
        "console_scripts": [
            "process_job=process_job:main",
        ],
    },
)
