"""The Tago integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, ATTR_ID

import logging
import threading
import socket
import struct
import websocket
import time
import json

from .const import DOMAIN

PLATFORMS: list[str] = ["light"]

_LOGGER = logging.getLogger(__name__)

_thread = None

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Tago integration from YAML (if present)."""
    _LOGGER.info('Tago Integration setup v1.2')
    
    cfg = config.get(DOMAIN)
    _LOGGER.info('Host cfg {}'.format(cfg))
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tago from a config entry."""
    config = entry.data
    host = config[CONF_HOST]
    
    _LOGGER.info('Bridge address {}'.format(host))

    # Replace async_setup_platforms with async_forward_entry_setups
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    global _thread
    _thread = ButtonThread(hass, host)
    _thread.start()
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    global _thread
    if _thread:
        _thread.stop()
        _thread.join()
    
    return unload_ok

class ButtonThread(threading.Thread):
    def __init__(self, hass, host, retry=5):
        threading.Thread.__init__(self)
        self.run_thread = True
        self.retry = retry
        self.host = host
        self.port = 8000
        self.hass = hass
        self.ws = None

    def on_message(self, ws, message):
        _LOGGER.info(message)
        msg = json.loads(message)      
        for m in msg:
            if m['event'] == 'keypress':
                data = {
                    ATTR_ID: 'tg-{}'.format(m['ts']), 
                    'action': 'single', 
                    'keypad': '0x{:2x}'.format(m['keypad']), 
                    'key': m['key'], 
                    'duration': 'long' if m['duration'] > 1 else 'short'
                }
                self.hass.bus.fire("tago_event", data)

    def on_error(self, ws, error):
        _LOGGER.info(error)

    def on_close(self, ws, close_status_code, close_msg):
        _LOGGER.info("### closed {} {} ###".format(close_status_code, close_msg))

    def stop(self):
        self.run_thread = False
        if self.ws:
            self.ws.close()

    def run(self):
        while self.run_thread:
            try:
                _LOGGER.info("Connecting to bridge {host} {port}".format(host=self.host, port=self.port))
                self.ws = websocket.WebSocketApp(
                    "ws://{host}:{port}/".format(host=self.host, port=self.port),
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                self.ws.run_forever()
            except Exception as e:
                _LOGGER.error(e)
            finally:
                if self.run_thread:
                    time.sleep(self.retry)
        
        _LOGGER.warning('Exiting')
