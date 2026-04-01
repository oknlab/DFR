from dfr.conf import DFRConfig
from dfr.exceptions import ConfigurationError, DFRException


def test_config_defaults() -> None:
    conf = DFRConfig(django_settings_module="example.settings")
    assert conf.orm_executor_workers == 16
    assert conf.openapi_enabled is True


def test_exception_hierarchy() -> None:
    assert issubclass(ConfigurationError, DFRException)
