"""Bundle RapidOCR configuration and ONNX models for offline packaged OCR."""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("rapidocr_onnxruntime")
hiddenimports = collect_submodules("rapidocr_onnxruntime")
