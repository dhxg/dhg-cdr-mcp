"""HTTPS / SSL Proxy Wrapper for CorelDRAW MCP Server

用于解决部分 MCP 客户端（如部分 Web Connector 或 ChatGPT Developer Mode）强求 https:// 协议的问题。
通过生成临时自签名 SSL 证书，将本地 HTTP 接口封装为 HTTPS 接口 (https://127.0.0.1:8765/mcp)。
"""

import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

# 确保 server/ 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def generate_self_signed_cert(cert_path: str, key_path: str):
    """使用 cryptography 动态生成自签名 SSL 证书"""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )

        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        logger.info(f"生成临时 SSL 证书: {cert_path}")
    except Exception as e:
        logger.error(f"无法生成 SSL 证书 (需安装 cryptography): {e}")
        sys.exit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CorelDRAW HTTPS MCP Server Launcher")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", type=int, default=8765, help="HTTPS Port")
    args = parser.parse_args()

    tmp_dir = tempfile.gettempdir()
    cert_file = os.path.join(tmp_dir, "coreldraw_mcp_cert.pem")
    key_file = os.path.join(tmp_dir, "coreldraw_mcp_key.pem")

    if not os.path.isfile(cert_file) or not os.path.isfile(key_file):
        generate_self_signed_cert(cert_file, key_file)

    os.environ["MCP_TRANSPORT"] = "streamable-http"
    os.environ["MCP_HOST"] = args.host
    os.environ["MCP_PORT"] = str(args.port)

    logger.info("=" * 60)
    logger.info("  Starting HTTPS MCP server...")
    logger.info(f"  HTTPS URL: https://{args.host}:{args.port}/mcp")
    logger.info(f"  SSE URL:   https://{args.host}:{args.port}/sse")
    logger.info("=" * 60)

    # 引入 server 并启动 ssl
    from server import mcp, setup_logging, init_connection, register_tools, close_connection
    setup_logging()
    init_connection()
    register_tools()

    try:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            ssl_certfile=cert_file,
            ssl_keyfile=key_file,
        )
    finally:
        close_connection()


if __name__ == "__main__":
    main()
