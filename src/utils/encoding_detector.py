# src/utils/encoding_detector.py

import chardet
from src.utils.logger import logger

def detect_file_encoding(file_path: str) -> str:
    """
    Detect the encoding of a file.
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        str: Detected encoding or 'utf-8' as fallback
    """
    try:
        with open(file_path, 'rb') as f:
            raw = f.read(10000)  # Read first 10KB
        # Fast path: UTF-8 is common; if it decodes, use it without chardet
        try:
            raw.decode('utf-8')
            return 'utf-8'
        except Exception:
            pass
        result = chardet.detect(raw)
        enc = result.get('encoding') or 'utf-8'
        return enc
    except Exception as e:
        logger.error(f"Failed to detect encoding for {file_path}: {str(e)}")
        return 'utf-8'
