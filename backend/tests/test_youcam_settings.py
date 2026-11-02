from app.config import Settings, get_settings


def test_documented_you_cam_env_names_are_read(monkeypatch):
    monkeypatch.setenv("YOU_CAM_API_KEY", " secret-from-docs ")
    monkeypatch.setenv("YOU_CAM_ENABLED_CATEGORIES", "upper_body, full_body, outer")
    monkeypatch.setenv("YOU_CAM_UNIT_COST", "2")
    monkeypatch.delenv("YOUCAM_API_KEY", raising=False)
    monkeypatch.delenv("YOUCAM_ENABLED_CATEGORIES", raising=False)
    get_settings.cache_clear()
    settings = Settings()
    assert settings.youcam_api_key == "secret-from-docs"
    assert settings.youcam_category_list == ["upper_body", "full_body", "outer"]
    assert settings.missing_youcam() is None


def test_pydantic_youcam_env_names_still_work(monkeypatch):
    monkeypatch.delenv("YOU_CAM_API_KEY", raising=False)
    monkeypatch.delenv("YOU_CAM_ENABLED_CATEGORIES", raising=False)
    monkeypatch.setenv("YOUCAM_API_KEY", "secret-pydantic")
    monkeypatch.setenv("YOUCAM_ENABLED_CATEGORIES", "upper_body")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.youcam_api_key == "secret-pydantic"
    assert settings.youcam_category_list == ["upper_body"]
    assert settings.missing_youcam() is None


def test_closet_category_names_map_to_youcam(monkeypatch):
    monkeypatch.setenv("YOU_CAM_API_KEY", "k")
    monkeypatch.setenv("YOU_CAM_ENABLED_CATEGORIES", "top,dress,outerwear")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.youcam_category_list == ["upper_body", "full_body", "outer"]
    assert settings.missing_youcam() is None


def test_empty_categories_still_block_youcam(monkeypatch):
    monkeypatch.setenv("YOU_CAM_API_KEY", "k")
    monkeypatch.setenv("YOU_CAM_ENABLED_CATEGORIES", "")
    get_settings.cache_clear()
    settings = Settings()
    missing = settings.missing_youcam()
    assert missing is not None
    assert "YOU_CAM_ENABLED_CATEGORIES" in missing
