import asyncio
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class FakeAiohttpModule(types.ModuleType):
    def __init__(self):
        super().__init__("aiohttp")
        self.BasicAuth = type(
            "BasicAuth", (), {"__init__": lambda self, *args, **kwargs: None}
        )
        self.ClientTimeout = type(
            "ClientTimeout", (), {"__init__": lambda self, total=None: None}
        )


sys.modules.setdefault("aiohttp", FakeAiohttpModule())


class FakeHomeAssistantModule(types.ModuleType):
    def __init__(self):
        super().__init__("homeassistant")
        self.__path__ = []


homeassistant = FakeHomeAssistantModule()
sys.modules["homeassistant"] = homeassistant

const = types.ModuleType("homeassistant.const")
const.Platform = type("Platform", (), {"SENSOR": "sensor", "CLIMATE": "climate"})
const.ATTR_TEMPERATURE = "temperature"
const.UnitOfTemperature = type("UnitOfTemperature", (), {"CELSIUS": "°C"})
const.PERCENTAGE = "%"
sys.modules["homeassistant.const"] = const

config_entries = types.ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = type("ConfigEntry", (), {})
sys.modules["homeassistant.config_entries"] = config_entries

core = types.ModuleType("homeassistant.core")
core.HomeAssistant = type("HomeAssistant", (), {})
core.callback = lambda func: func
sys.modules["homeassistant.core"] = core

helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
sys.modules["homeassistant.helpers"] = helpers

config_validation = types.ModuleType("homeassistant.helpers.config_validation")
config_validation.config_entry_only_config_schema = lambda domain: None
sys.modules["homeassistant.helpers.config_validation"] = config_validation
helpers.config_validation = config_validation

components = types.ModuleType("homeassistant.components")
components.__path__ = []
sys.modules["homeassistant.components"] = components

climate_module = types.ModuleType("homeassistant.components.climate")
climate_module.ClimateEntity = type("ClimateEntity", (), {})
climate_module.ClimateEntityFeature = type(
    "ClimateEntityFeature", (), {"TARGET_TEMPERATURE": "target_temperature"}
)
climate_module.HVACMode = type(
    "HVACMode", (), {"HEAT": "heat", "COOL": "cool", "OFF": "off"}
)
sys.modules["homeassistant.components.climate"] = climate_module

entity = types.ModuleType("homeassistant.helpers.entity")
entity.DeviceInfo = type("DeviceInfo", (dict,), {})
sys.modules["homeassistant.helpers.entity"] = entity

aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")


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
        return {
            "can_make_permanent_changes": False,
            "can_make_temporary_changes": False,
        }


class FakeSession:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, *args, **kwargs):
        self.calls.append(url)
        return FakeResponse(200)

    def post(self, url, *args, **kwargs):
        self.calls.append(url)
        return FakeResponse(200)


aiohttp_client.async_get_clientsession = lambda hass: FakeSession()
sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

exceptions = types.ModuleType("homeassistant.exceptions")
exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
sys.modules["homeassistant.exceptions"] = exceptions

update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
update_coordinator.DataUpdateCoordinator = type(
    "DataUpdateCoordinator",
    (),
    {
        "__init__": lambda self, *args, **kwargs: None,
        "__class_getitem__": classmethod(lambda cls, item: cls),
    },
)
update_coordinator.CoordinatorEntity = type(
    "CoordinatorEntity",
    (),
    {
        "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
        "async_write_ha_state": lambda self: None,
    },
)
update_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

from custom_components.controme.coordinator import ContromeDataUpdateCoordinator  # noqa: E402
from custom_components.controme.climate import ContromeClimate  # noqa: E402


class FakeHass:
    def __init__(self):
        self.loop = types.SimpleNamespace(time=lambda: 0.0)


class FakeCoordinator:
    def __init__(self):
        self.permissions = {
            "can_make_temporary_changes": False,
            "can_make_permanent_changes": False,
        }
        self.data = []
        self.async_refresh = lambda: None


def test_climate_blocks_temperature_write_when_permissions_forbid_it():
    async def _run():
        coordinator = FakeCoordinator()
        climate = ContromeClimate(
            coordinator,
            types.SimpleNamespace(
                data={
                    "api_url": "http://example",
                    "haus_id": "1",
                    "user": "u",
                    "password": "p",
                },
                options={},
            ),
            {"id": "7", "floor_id": "2", "temperatur": 21.0, "solltemperatur": 20.0},
            None,
        )
        climate.hass = FakeHass()
        await climate.async_set_temperature(temperature=22.0)
        return climate

    climate = asyncio.run(_run())
    assert climate._attr_target_temperature == 20.0
