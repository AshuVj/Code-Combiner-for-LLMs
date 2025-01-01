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
            rawdata = f.read(10000)  # Read first 10KB
        result = chardet.detect(rawdata)
        encoding = result['encoding']
        if not encoding:
            encoding = 'utf-8'
        return encoding
    except Exception as e:
        logger.error(f"Failed to detect encoding for {file_path}: {str(e)}")
        return 'utf-8'
