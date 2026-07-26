"""Diagnostics support for Controme."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from .const import DOMAIN, CONF_API_URL, CONF_HAUS_ID, CONF_USER


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": {
            CONF_API_URL: entry.data[CONF_API_URL],
            CONF_HAUS_ID: entry.data[CONF_HAUS_ID],
            CONF_USER: entry.data[CONF_USER],
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
        "data": coordinator.data,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict:
    """Return diagnostics for a device."""
    coordinator = entry.runtime_data
    return {
        "device": {
            "identifiers": list(device.identifiers),
            "name": device.name,
            "model": device.model,
            "via_device_id": device.via_device_id,
        },
        "coordinator_data": coordinator.data,
    }
