"""Config flow for Controme integration."""

import logging
from typing import Any, Optional
import voluptuous as vol
import aiohttp
from aiohttp import ClientTimeout
import asyncio
from urllib.parse import urlparse
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import (
    DOMAIN,
    CONF_API_URL,
    CONF_HAUS_ID,
    CONF_USER,
    CONF_PASSWORD,
    CONF_USE_DEFAULT_DURATION,
    CONF_DURATION_MINUTES,
    CONF_DURATION_OPTION,
)
from .helpers import scan_network

_LOGGER = logging.getLogger(__name__)

# Schema for manual entry
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_URL): str,
        vol.Required(CONF_USER): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_HAUS_ID, default="1"): str,
        vol.Optional(CONF_USE_DEFAULT_DURATION, default=True): bool,
        vol.Optional(CONF_DURATION_MINUTES, default=30): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
    }
)

# Schema for credentials after auto-discovery
CREDENTIALS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USER): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_HAUS_ID, default="1"): str,
        vol.Optional(CONF_USE_DEFAULT_DURATION, default=True): bool,
        vol.Optional(CONF_DURATION_MINUTES, default=30): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
    }
)


class ContromeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Controme."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_systems = []
        self._user_input = {}
        self._scan_already_run = False
        self._reauth_entry = None

    async def async_step_user(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return await self._process_user_input(user_input)

        self._scan_already_run = False
        return self.async_show_menu(
            step_id="user",
            menu_options=["auto_discovery", "manual_entry"],
        )

    async def async_step_auto_discovery(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle automatic discovery of Controme systems."""
        # Check if we've already run a scan in this flow
        if self._scan_already_run:
            _LOGGER.warning("Scan already run, using cached results")
            # Use cached results instead of running another scan
            return self._show_form_after_scan()

        # Mark that we're running a scan
        self._scan_already_run = True

        # Run the scan directly instead of using a progress task
        await self._async_scan_systems()

        # Show the appropriate form based on scan results
        return self._show_form_after_scan()

    def _show_form_after_scan(self) -> FlowResult:
        """Show the appropriate form based on scan results."""
        if self._discovered_systems:
            # If we found exactly one system, go directly to credentials entry
            if len(self._discovered_systems) == 1:
                system = self._discovered_systems[0]
                return self.async_show_form(
                    step_id="credentials",
                    description_placeholders={"system": system["title"]},
                    data_schema=CREDENTIALS_DATA_SCHEMA,
                )
            # If we found multiple systems, show selection screen
            else:
                system_options = {
                    system["url"]: system["title"]
                    for system in self._discovered_systems
                }
                return self.async_show_form(
                    step_id="select_system",
                    description_placeholders={
                        "count": str(len(self._discovered_systems))
                    },
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_API_URL): vol.In(system_options),
                            vol.Required(CONF_USER): str,
                            vol.Required(CONF_PASSWORD): str,
                            vol.Optional(CONF_HAUS_ID, default="1"): str,
                        }
                    ),
                )

        # No systems found, fall back to manual entry
        _LOGGER.warning(
            "No Controme systems found during scan. Falling back to manual entry."
        )
        return self.async_show_form(
            step_id="manual_entry",
            description_placeholders={
                "error": "No systems found automatically. Please enter details manually."
            },
            data_schema=STEP_USER_DATA_SCHEMA,
        )

    async def _async_scan_systems(self) -> None:
        """Perform the actual network scan."""
        try:
            _LOGGER.info("Starting network scan for Controme systems...")
            # Clear any previous results
            self._discovered_systems = []
            # Run the scan with a 30-second timeout
            self._discovered_systems = await asyncio.wait_for(
                scan_network(), timeout=30
            )
            _LOGGER.info(
                "Network scan complete. Found %d systems", len(self._discovered_systems)
            )
        except Exception as err:
            _LOGGER.error("Error scanning network: %s", err)
            self._discovered_systems = []

    async def async_step_select_system(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle selection of a system when multiple are discovered."""
        if user_input is None:
            return self.async_abort(reason="unknown")

        return await self._process_user_input(user_input)

    async def async_step_credentials(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle credential entry for a discovered system."""
        errors = {}

        if user_input is None:
            # Show the credentials form
            return self.async_show_form(
                step_id="credentials",
                description_placeholders={
                    "system": self._discovered_systems[0]["title"]
                },
                data_schema=CREDENTIALS_DATA_SCHEMA,
                errors=errors,
            )

        # User has provided credentials
        system = self._discovered_systems[0]
        user_input[CONF_API_URL] = system["url"]

        # Test the connection with the provided credentials
        return await self._process_user_input(user_input)

    async def async_step_manual_entry(
        self, user_input: Optional[dict[str, Any]] = None
    ) -> FlowResult:
        """Handle manual entry of Controme system details."""
        errors = {}

        if user_input is None:
            # Show the manual entry form directly
            return self.async_show_form(
                step_id="manual_entry", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        # User has provided manual details
        return await self._process_user_input(user_input)

    async def _process_user_input(self, user_input: dict[str, Any]) -> FlowResult:
        """Process the user input and create or update the config entry."""
        errors = {}

        if user_input.get(CONF_USE_DEFAULT_DURATION, True):
            duration = "default"
        else:
            try:
                duration = str(user_input[CONF_DURATION_MINUTES])
            except (KeyError, ValueError):
                errors["base"] = "invalid_duration"

        if not errors:
            try:
                session = async_get_clientsession(self.hass)
                base_url = user_input[CONF_API_URL]
                if not base_url.startswith(("http://", "https://")):
                    base_url = f"http://{base_url}"

                house_id = user_input.get(CONF_HAUS_ID, "1")
                url = f"{base_url.rstrip('/')}/get/json/v1/{house_id}/temps/"

                async with session.get(
                    url,
                    auth=aiohttp.BasicAuth(
                        user_input[CONF_USER], user_input[CONF_PASSWORD]
                    ),
                    timeout=ClientTimeout(total=10),
                ) as response:
                    if response.status == 401:
                        errors["base"] = "invalid_auth"
                    elif response.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        if self._reauth_entry is not None:
                            self.hass.config_entries.async_update_entry(
                                self._reauth_entry,
                                data={
                                    CONF_API_URL: base_url,
                                    CONF_USER: user_input[CONF_USER],
                                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                                    CONF_HAUS_ID: house_id,
                                },
                                options={
                                    CONF_DURATION_OPTION: duration,
                                },
                            )
                            await self.hass.config_entries.async_reload(
                                self._reauth_entry.entry_id
                            )
                            return self.async_abort(reason="reauth_successful")

                        unique_id = self._build_unique_id(base_url, house_id)
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Controme ({base_url})",
                            data={
                                CONF_API_URL: base_url,
                                CONF_USER: user_input[CONF_USER],
                                CONF_PASSWORD: user_input[CONF_PASSWORD],
                                CONF_HAUS_ID: house_id,
                            },
                            options={
                                CONF_DURATION_OPTION: duration,
                            },
                        )
            except Exception as err:
                _LOGGER.error("Error testing connection: %s", err)
                errors["base"] = "cannot_connect"

        if self._reauth_entry is not None:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_USER, default=self._reauth_entry.data[CONF_USER]
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(
                        CONF_HAUS_ID,
                        default=self._reauth_entry.data.get(CONF_HAUS_ID, "1"),
                    ): str,
                }
            )
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=schema,
                errors=errors,
                description_placeholders={
                    "api_url": self._reauth_entry.data[CONF_API_URL],
                },
            )

        return self.async_show_form(
            step_id="manual_entry",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the start of the reauthentication flow."""
        self._reauth_entry = self._get_reauth_entry()
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            user_input[CONF_API_URL] = self._reauth_entry.data[CONF_API_URL]
            return await self._process_user_input(user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USER, default=self._reauth_entry.data[CONF_USER]
                ): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_HAUS_ID,
                    default=self._reauth_entry.data.get(CONF_HAUS_ID, "1"),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            description_placeholders={
                "api_url": self._reauth_entry.data[CONF_API_URL],
            },
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the reauthentication confirmation step."""
        self._reauth_entry = self._get_reauth_entry()
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            user_input[CONF_API_URL] = self._reauth_entry.data[CONF_API_URL]
            return await self._process_user_input(user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USER, default=self._reauth_entry.data[CONF_USER]
                ): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_HAUS_ID,
                    default=self._reauth_entry.data.get(CONF_HAUS_ID, "1"),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            description_placeholders={
                "api_url": self._reauth_entry.data[CONF_API_URL],
            },
        )

    @staticmethod
    def _build_unique_id(base_url: str, house_id: str) -> str:
        """Build a unique ID from the Controme system URL and house ID."""
        host = urlparse(base_url).hostname or base_url
        return f"controme_{host}_{house_id}"

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return ContromeOptionsFlowHandler(config_entry)

    # Tell Home Assistant how to handle the progress screen
    @staticmethod
    def async_get_progress_steps() -> list[str]:
        """Return a list of steps that are shown while we're in progress."""
        return ["auto_discovery"]


class ContromeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Controme options to allow reconfiguration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the Controme options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get(CONF_USE_DEFAULT_DURATION, True):
                duration = "default"
            else:
                try:
                    duration = str(user_input[CONF_DURATION_MINUTES])
                except (KeyError, ValueError):
                    errors["base"] = "invalid_duration"

            if not errors:
                try:
                    session = async_get_clientsession(self.hass)
                    base_url = user_input[CONF_API_URL]
                    if not base_url.startswith(("http://", "https://")):
                        base_url = f"http://{base_url}"

                    house_id = user_input.get(CONF_HAUS_ID, "1")
                    url = f"{base_url.rstrip('/')}/get/json/v1/{house_id}/temps/"

                    async with session.get(
                        url,
                        auth=aiohttp.BasicAuth(
                            user_input[CONF_USER], user_input[CONF_PASSWORD]
                        ),
                        timeout=ClientTimeout(total=10),
                    ) as response:
                        if response.status == 401:
                            errors["base"] = "invalid_auth"
                        elif response.status != 200:
                            errors["base"] = "cannot_connect"
                        else:
                            self.hass.config_entries.async_update_entry(
                                self._config_entry,
                                data={
                                    CONF_API_URL: base_url,
                                    CONF_USER: user_input[CONF_USER],
                                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                                    CONF_HAUS_ID: house_id,
                                },
                                options={
                                    CONF_DURATION_OPTION: duration,
                                },
                            )
                            await self.hass.config_entries.async_reload(
                                self._config_entry.entry_id
                            )
                            return self.async_create_entry(title="", data={})
                except Exception:
                    errors["base"] = "cannot_connect"

        current_use_default = (
            self._config_entry.options.get(CONF_DURATION_OPTION, "default") == "default"
        )
        current_minutes = 30
        if not current_use_default:
            try:
                current_minutes = int(
                    self._config_entry.options.get(CONF_DURATION_OPTION, "30")
                )
            except (ValueError, TypeError):
                current_minutes = 30

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_URL,
                    default=self._config_entry.data[CONF_API_URL],
                ): str,
                vol.Required(
                    CONF_USER,
                    default=self._config_entry.data[CONF_USER],
                ): str,
                vol.Required(
                    CONF_PASSWORD,
                    default=self._config_entry.data[CONF_PASSWORD],
                ): str,
                vol.Optional(
                    CONF_HAUS_ID,
                    default=self._config_entry.data.get(CONF_HAUS_ID, "1"),
                ): str,
                vol.Optional(
                    CONF_USE_DEFAULT_DURATION,
                    default=current_use_default,
                ): bool,
                vol.Optional(
                    CONF_DURATION_MINUTES,
                    default=current_minutes,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
