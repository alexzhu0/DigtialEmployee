import uvicorn
import ssl
from pathlib import Path
from app.web.server import app
from app.core.database import init_db
from config.config import settings

def setup_ssl():
    """设置SSL证书"""
    ssl_dir = Path("ssl")
    if not ssl_dir.exists():
        ssl_dir.mkdir()
        
    cert_path = ssl_dir / "cert.pem"
    key_path = ssl_dir / "key.pem"
    
    if not cert_path.exists() or not key_path.exists():
        print("请先生成SSL证书！")
        print("运行以下命令：")
        print("openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes")
        exit(1)

def setup_temp_dir():
    """设置临时文件目录"""
    temp_dir = Path("temp")
    if not temp_dir.exists():
        temp_dir.mkdir()

def main():
    # 初始化数据库
    init_db()
    
    # 设置SSL
    setup_ssl()
    
    # 设置临时目录
    setup_temp_dir()
    
    # 启动服务器
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(
        settings.SSL_CERT_PATH,
        settings.SSL_KEY_PATH
    )
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        ssl_certfile=settings.SSL_CERT_PATH,
        ssl_keyfile=settings.SSL_KEY_PATH
    )

if __name__ == "__main__":
    main() 