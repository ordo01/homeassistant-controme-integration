import asyncio
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    const = types.ModuleType("homeassistant.const")

    class Platform:
        SENSOR = "sensor"
        CLIMATE = "climate"

    const.Platform = Platform
    sys.modules["homeassistant.const"] = const

    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

        def __init__(self, *args, **kwargs):
            self.hass = None

        def async_show_form(
            self, *, step_id, data_schema, errors=None, description_placeholders=None
        ):
            return {
                "type": "form",
                "step_id": step_id,
                "errors": errors or {},
                "description_placeholders": description_placeholders or {},
            }

        def async_abort(self, *, reason):
            return {"type": "abort", "reason": reason}

        def async_create_entry(self, *, title, data, options=None):
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
                "options": options or {},
            }

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            return None

        def _get_reauth_entry(self):
            return getattr(self, "_reauth_entry", None)

    class OptionsFlow:
        def __init__(self, *args, **kwargs):
            self.hass = None

    class ConfigEntry:
        pass

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigEntry = ConfigEntry
    sys.modules["homeassistant.config_entries"] = config_entries

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    core.HomeAssistant = HomeAssistant
    core.callback = lambda func: func
    sys.modules["homeassistant.core"] = core

    data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers

    config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    config_validation.config_entry_only_config_schema = lambda domain: None
    sys.modules["homeassistant.helpers.config_validation"] = config_validation

    device_registry = types.ModuleType("homeassistant.helpers.device_registry")

    class FakeDeviceRegistry:
        def async_get_or_create(self, **kwargs):
            return {"identifiers": kwargs.get("identifiers", ())}

    device_registry.async_get = lambda hass: FakeDeviceRegistry()
    sys.modules["homeassistant.helpers.device_registry"] = device_registry

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, url, *args, **kwargs):
            self.calls.append((url, args, kwargs))
            return FakeResponse(200)

        def post(self, url, *args, **kwargs):
            self.calls.append((url, args, kwargs))
            return FakeResponse(200)

    class FakeResponse:
        def __init__(self, status):
            self.status = status
            self._text = "{}"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def text(self):
            return self._text

        async def json(self):
            return []

    aiohttp_client.async_get_clientsession = lambda hass: FakeSession()
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})
    exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    sys.modules["homeassistant.exceptions"] = exceptions

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __init__(self, *args, **kwargs):
            self.data = None
            self.last_update_success = True
            self.update_interval = None

        def __class_getitem__(cls, item):
            return cls

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    class UpdateFailed(Exception):
        pass

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    update_coordinator.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


class FakeBasicAuth:
    def __init__(self, username, password):
        self.username = username
        self.password = password


class FakeClientTimeout:
    def __init__(self, total):
        self.total = total


class FakeAiohttpModule(types.ModuleType):
    def __init__(self):
        super().__init__("aiohttp")
        self.BasicAuth = FakeBasicAuth
        self.ClientTimeout = FakeClientTimeout
        self.ClientSession = type("ClientSession", (), {})
        self.TCPConnector = type(
            "TCPConnector", (), {"__init__": lambda self, **kwargs: None}
        )
        self.ClientConnectorError = type("ClientConnectorError", (Exception,), {})


class FakeVoluptuous(types.ModuleType):
    def __init__(self):
        super().__init__("voluptuous")

    class Schema:
        def __init__(self, schema):
            self.schema = schema

    class Required:
        def __init__(self, key, default=None):
            self.key = key
            self.default = default

    class Optional:
        def __init__(self, key, default=None):
            self.key = key
            self.default = default

    class In:
        def __init__(self, options):
            self.options = options

    class All:
        def __init__(self, *args):
            self.args = args

    class Range:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Coerce:
        def __init__(self, func):
            self.func = func


_install_homeassistant_stubs()
sys.modules.setdefault("aiohttp", FakeAiohttpModule())
sys.modules.setdefault("voluptuous", FakeVoluptuous())

from custom_components.controme.config_flow import (  # noqa: E402
    CONF_API_URL,
    CONF_HAUS_ID,
    CONF_PASSWORD,
    CONF_USER,
    ContromeConfigFlow,
)


class FakeConfigEntries:
    def __init__(self):
        self.updated_entry = None
        self.reloaded_entry_id = None

    def async_update_entry(self, entry, *, data=None, options=None):
        self.updated_entry = entry
        entry.data = data or entry.data
        entry.options = options or entry.options

    async def async_reload(self, entry_id):
        self.reloaded_entry_id = entry_id


class FakeHass:
    def __init__(self):
        self.config_entries = FakeConfigEntries()


def test_credentials_step_creates_entry():
    async def _run():
        flow = ContromeConfigFlow()
        flow.hass = FakeHass()
        flow._discovered_systems = [
            {"url": "http://controme.local", "title": "Controme"}
        ]

        result = await flow.async_step_credentials(
            {
                CONF_USER: "demo",
                CONF_PASSWORD: "secret",
                CONF_HAUS_ID: "2",
            }
        )
        return result

    result = asyncio.run(_run())

    assert result["type"] == "create_entry"
    assert result["data"][CONF_API_URL] == "http://controme.local"
    assert result["data"][CONF_USER] == "demo"
    assert result["data"][CONF_HAUS_ID] == "2"


def test_reauth_updates_existing_entry_and_aborts_successfully():
    async def _run():
        flow = ContromeConfigFlow()
        flow.hass = FakeHass()

        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                CONF_API_URL: "http://oldhost",
                CONF_USER: "old-user",
                CONF_PASSWORD: "old-pass",
                CONF_HAUS_ID: "1",
            },
            options={},
        )
        flow._reauth_entry = entry

        result = await flow.async_step_reauth_confirm(
            {
                CONF_USER: "new-user",
                CONF_PASSWORD: "new-pass",
                CONF_HAUS_ID: "3",
            }
        )
        return result, entry

    result, entry = asyncio.run(_run())

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_USER] == "new-user"
    assert entry.data[CONF_PASSWORD] == "new-pass"
    assert entry.data[CONF_HAUS_ID] == "3"
