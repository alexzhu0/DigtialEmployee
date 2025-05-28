import uvicorn
import ssl
from pathlib import Path
from app.web.server import app # app is imported for uvicorn.run
from app.core.database import init_db
from config.config import settings
from config.logging_config import setup_logging, get_logger

# Get a logger for the main module
logger = get_logger(__name__)

def setup_ssl():
    """设置SSL证书"""
    logger.info("Setting up SSL...")
    ssl_dir = Path("ssl")
    if not ssl_dir.exists():
        ssl_dir.mkdir()
        logger.debug(f"Created SSL directory: {ssl_dir.resolve()}")
        
    cert_path = ssl_dir / "cert.pem"
    key_path = ssl_dir / "key.pem"
    
    if not cert_path.exists() or not key_path.exists():
        logger.critical("SSL certificate or key not found!")
        logger.critical(f"Please ensure '{cert_path.name}' and '{key_path.name}' exist in '{ssl_dir.resolve()}'.")
        logger.critical("To generate: openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes")
        exit(1)
    logger.info("SSL setup complete.")

def setup_temp_dir():
    """设置临时文件目录"""
    logger.info("Setting up temporary directory...")
    temp_dir = Path("temp")
    if not temp_dir.exists():
        temp_dir.mkdir()
        logger.debug(f"Created temporary directory: {temp_dir.resolve()}")
    logger.info("Temporary directory setup complete.")

def main():
    # Initialize logging as the first step
    # Log level can be read from settings.LOG_LEVEL if defined in Settings
    setup_logging(log_level="INFO") 
    
    logger.info("Application starting...")
    
    # 初始化数据库
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialization complete.")
    
    # 设置SSL
    setup_ssl()
    
    # 设置临时目录
    setup_temp_dir()
    
    # 启动服务器
    logger.info("Preparing SSL context for Uvicorn...")
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain(
            settings.SSL_CERT_PATH,
            settings.SSL_KEY_PATH
        )
        logger.info("SSL context loaded successfully.")
    except FileNotFoundError:
        logger.critical(f"SSL certificate or key file not found at specified paths: {settings.SSL_CERT_PATH}, {settings.SSL_KEY_PATH}")
        exit(1)
    except ssl.SSLError as e:
        logger.critical(f"SSL error during context loading: {e}")
        exit(1)

    logger.info(f"Starting Uvicorn server on {settings.HOST}:{settings.PORT} with SSL.")
    try:
        uvicorn.run(
            "app.web.server:app", # Changed to string to allow reload if uvicorn --reload is used, and standard practice
            host=settings.HOST,
            port=settings.PORT,
            ssl_certfile=settings.SSL_CERT_PATH,
            ssl_keyfile=settings.SSL_KEY_PATH,
            # log_config=None # We are using our own logging setup
        )
    except Exception as e:
        logger.critical(f"Failed to start Uvicorn server: {e}", exc_info=True)
        # exc_info=True will log the full exception traceback
    finally:
        logger.info("Application shutting down...") # This will only be logged if uvicorn stops gracefully or an exception occurs

if __name__ == "__main__":
    main()