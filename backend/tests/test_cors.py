from app.config import Settings


def test_cors_includes_loopback_aliases_and_frontend_origin():
    settings = Settings(
        cors_origins="http://localhost:3000",
        frontend_origin="https://closest-chemistry.vercel.app",
        database_url="sqlite+pysqlite:///:memory:",
        database_ssl_require=False,
    )
    origins = settings.cors_origin_list
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "https://closest-chemistry.vercel.app" in origins
