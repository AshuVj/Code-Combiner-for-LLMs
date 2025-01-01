# src/main.py

from src.utils.logger import logger
from src.app import FileCombinerApp

def main():
    logger.info("Application started.")
    try:
        app = FileCombinerApp()
        app.run()
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        logger.info("Application terminated.")

if __name__ == "__main__":
    main()
