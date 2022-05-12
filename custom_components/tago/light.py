"""Platform for light integration."""
from __future__ import annotations

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    SUPPORT_BRIGHTNESS,
    SUPPORT_TRANSITION,
    COLOR_MODE_BRIGHTNESS,
    LightEntity,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import asyncio
import aiohttp
from aiohttp.hdrs import AUTHORIZATION, USER_AGENT
import async_timeout

_LOGGER = logging.getLogger(__name__)

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    _LOGGER.info('Setup Platform')

async def _list_devices(
    baseUrl,
    session: aiohttp.ClientSession,
    timeout: int,
):
    url = '{}/api/list_devices'.format(baseUrl)

    try:
        async with async_timeout.timeout(timeout):
            resp = await session.get(url)
            result = await resp.json()

            return result

    except aiohttp.ClientError:
        _LOGGER.warning("Can't connect to bridge")

    except asyncio.TimeoutError:
        _LOGGER.warning("Timeout waiting for bridge")

    return None

async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    config = entry.data
    host = config[CONF_HOST]
    port = 5000

    # # Add devices
    session = hass.helpers.aiohttp_client.async_get_clientsession()

    urlBase = 'http://{}:{}'.format(host, port)
    _LOGGER.info('Setup entry {}'.format(urlBase))

    result = await _list_devices(urlBase, session, 10)
    if not result:
        return False

    entities = []
    for device in result:
        if 'dimmers' in result[device]:
            dimmers = result[device]['dimmers']
            for d in dimmers:
                entities.append(TagoLight(host,
                                          port,
                                          device, 
                                          dimmers[d]['ch'],
                                          d, 
                                          dimmers[d].get('alias', '{}_ch{}'.format(device, dimmers[d]['ch']))))
    
    if len(entities):
        async_add_entities(entities)

import http.client
import json

class TagoLight(LightEntity):
    """Representation of a Tago Light, including dimmable."""
    def __init__(self, host, port, tid, ch, uid, name):
        self._port = port
        self._host = host
        self._tid = tid
        self._ch = ch
        self._name = name
        self._uid = uid
        self._prev_brightness = 0
        self._brightness = 0

        self._attr_supported_color_modes = {COLOR_MODE_BRIGHTNESS}
        self._attr_color_mode = COLOR_MODE_BRIGHTNESS

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION

    @property
    def name(self):
        return self._name

    @property
    def available(self):
        return True

    @property
    def unique_id(self):
        return self._uid

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    # @property
    # def should_poll(self):
    #     """No polling needed."""
    #     return False

    def turn_on(self, **kwargs):
        """Turn the light on."""
        if ATTR_TRANSITION in kwargs:
            transition_time = kwargs[ATTR_TRANSITION]
        else:
            transition_time = 50

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
        elif self._prev_brightness == 0:
            brightness = 255 / 2
        else:
            brightness = self._prev_brightness

        self._prev_brightness = brightness
        self._brightness = brightness
        _LOGGER.info('TAGO: turn_on')
        self.set_level(self._brightness, transition_time)

    def turn_off(self, **kwargs):
        if ATTR_TRANSITION in kwargs:
            transition_time = kwargs[ATTR_TRANSITION]
        else: 
            transition_time = 50

        """Turn the light off."""
        _LOGGER.info('TAGO: turn_off')
        self._brightness = 0
        self.set_level(self._brightness, transition_time)

    @property
    def is_on(self):
        """Return true if device is on."""
        # _LOGGER.info('TAGO: is on? {}'.format(self._brightness > 0))
        return self._brightness > 0


    def set_level(self, level, transition_time) -> bool:
        level = int((level * 100) / 255)
        _LOGGER.info('TAGO: set light level {} t {}'.format(level, transition_time))

        try:
            conn = http.client.HTTPConnection(self._host, self._port)

            conn.request('POST', 
                            '/api/{}/do'.format(self._tid), 
                            json.dumps([{'action': 'RAMP_TO', 'value': level, 'rate': 50, 'ch': self._ch}]), 
                            {'Content-type': 'application/json'})
            response = conn.getresponse()

            return True
        except Exception as e:
            print(e)

        return False

    def update(self):
        # _LOGGER.info('TAGO: update')
        """Call when forcing a refresh of the device."""
        if self._prev_brightness is None:
            self._prev_brightness = 255