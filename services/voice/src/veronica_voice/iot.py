"""Veronica Tactical IoT & Smart Home Security Bridge.

Provides secure local-network IoT control (Home Assistant REST API, Shelly, Tasmota,
WLED, and custom LAN webhooks) with zero-trust security guardrails:
  * Anti-SSRF private-LAN enforcement (RFC1918 / mDNS .local only by default)
  * High-risk physical access gate (locks, garage doors, security alarms require confirm=True)
  * Tamper-evident JSONL security auditing for every IoT command
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from .audit_logger import record_audit_event

logger = logging.getLogger("veronica.iot")

IOT_DIR = Path.home() / ".veronica"
IOT_REGISTRY_FILE = IOT_DIR / "iot_devices.json"

HIGH_RISK_KEYWORDS = frozenset({
    "unlock", "disarm", "garage", "front_door", "back_door", "deadbolt", "security_alarm", "gate_open",
})


def is_safe_iot_endpoint(url_or_host: str) -> bool:
    """Verify that an IoT target is on the local private network (RFC1918 / loopback / .local)
    to prevent cloud prompt-injection SSRF attacks against external hosts.
    """
    raw = url_or_host.strip()
    if not raw:
        return False
    if "://" not in raw:
        raw = f"http://{raw}"
    try:
        parsed = urllib.parse.urlparse(raw)
        host = (parsed.hostname or "").lower().strip()
        if not host:
            return False
        if host in ("localhost", "homeassistant.local") or host.endswith(".local") or host.endswith(".lan"):
            return True
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _load_registry() -> dict[str, dict[str, Any]]:
    IOT_DIR.mkdir(parents=True, exist_ok=True)
    if not IOT_REGISTRY_FILE.exists():
        default_devices = {
            "desk_lights": {
                "name": "Desk Lights",
                "type": "homeassistant",
                "entity_id": "light.desk_lights",
                "room": "office",
                "high_risk": False,
            },
            "office_lamp": {
                "name": "Office Lamp",
                "type": "shelly",
                "host": "192.168.1.150",
                "room": "office",
                "high_risk": False,
            },
            "studio_led": {
                "name": "Studio WLED Strip",
                "type": "wled",
                "host": "192.168.1.151",
                "room": "office",
                "high_risk": False,
            },
            "front_door_lock": {
                "name": "Front Door Deadbolt",
                "type": "homeassistant",
                "entity_id": "lock.front_door",
                "room": "entrance",
                "high_risk": True,
            },
        }
        try:
            IOT_REGISTRY_FILE.write_text(json.dumps(default_devices, indent=2), encoding="utf-8")
        except Exception:
            pass
        return default_devices
    try:
        return json.loads(IOT_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_registry(reg: dict[str, dict[str, Any]]) -> None:
    IOT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        IOT_REGISTRY_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    except Exception:
        pass


def _probe_tcp(host: str, port: int = 80, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def iot_control(
    action: str = "list",
    device: str = "",
    state: str = "",
    host: str = "",
    device_type: str = "webhook",
    confirm: bool = False,
    *,
    target: str = "",
    endpoint: str = "",
    protocol: str = "",
    entity_id: str = "",
    confirm_security: bool = False,
) -> dict[str, Any]:
    """Unified IoT & Smart Home controller with security policy enforcement.

    Supported actions:
      - 'list': List registered IoT devices and Home Assistant connection state.
      - 'scan': Probe LAN reachability of registered local IP devices.
      - 'register': Add or update a smart device in ~/.veronica/iot_devices.json.
      - 'turn_on' / 'turn_off' / 'toggle' / 'unlock' / 'lock': Control a target device.
    """
    device = device or target
    host = host or endpoint
    device_type = protocol or device_type
    confirm = bool(confirm or confirm_security)
    clean_act = action.lower().strip()
    reg = _load_registry()
    ha_url = os.environ.get("HA_URL", "").strip()
    ha_token = os.environ.get("HA_TOKEN", "").strip()

    if clean_act == "list":
        record_audit_event("iot", "list_devices", "success", {"count": len(reg)})
        return {
            "status": "success",
            "action": "list",
            "home_assistant_configured": bool(ha_url and ha_token),
            "security_policy": "RFC1918 Private LAN Enforced + Physical Lock Confirmation Gate",
            "devices": reg,
            "count": len(reg),
        }

    if clean_act == "scan":
        scan_results: list[dict[str, Any]] = []
        for dev_id, info in reg.items():
            dev_host = info.get("host", "")
            reachable = False
            if dev_host and is_safe_iot_endpoint(dev_host):
                reachable = _probe_tcp(dev_host, int(info.get("port", 80)))
            scan_results.append({
                "id": dev_id,
                "name": info.get("name", dev_id),
                "type": info.get("type", "unknown"),
                "host": dev_host or info.get("entity_id", "hub"),
                "online": reachable,
            })
        record_audit_event("iot", "lan_scan", "success", {"scanned": len(scan_results)})
        return {
            "status": "success",
            "action": "scan",
            "results": scan_results,
            "message": f"Scanned {len(scan_results)} tactical IoT endpoints on local network.",
        }

    if clean_act == "register":
        dev_key = device.lower().strip().replace(" ", "_")
        if not dev_key:
            return {"status": "error", "message": "Device name required to register IoT endpoint."}
        if host and not is_safe_iot_endpoint(host):
            record_audit_event("iot_security", "blocked_non_private_host", "blocked", {"device": dev_key, "host": host})
            return {
                "status": "blocked",
                "message": f"Security Policy Violation: IoT host '{host}' rejected. Only RFC1918 private LAN or .local addresses are permitted.",
            }
        is_risk = any(k in dev_key for k in HIGH_RISK_KEYWORDS)
        reg[dev_key] = {
            "name": device.strip(),
            "type": device_type.lower().strip() or "webhook",
            "host": host.strip(),
            "entity_id": f"switch.{dev_key}",
            "high_risk": is_risk,
        }
        _save_registry(reg)
        record_audit_event("iot", "register_device", "success", {"device": dev_key, "type": device_type})
        return {
            "status": "success",
            "action": "register",
            "device": dev_key,
            "message": f"Registered IoT device '{device}' ({device_type}) in local security registry.",
        }

    # Device state control (turn_on, turn_off, toggle, lock, unlock)
    target_key = device.lower().strip().replace(" ", "_")
    matched_id = None
    matched_info = None
    for k, info in reg.items():
        if k == target_key or target_key in k or target_key in info.get("name", "").lower():
            matched_id = k
            matched_info = info
            break

    desired = (state or clean_act).lower().strip()
    if desired in ("on", "turn_on", "enable", "activate"):
        desired = "on"
    elif desired in ("off", "turn_off", "disable", "deactivate"):
        desired = "off"
    elif desired in ("toggle", "switch"):
        desired = "toggle"

    # Security Gate: Check if this is a high-risk physical security operation (unlock / disarm / garage)
    is_high_risk = (
        (matched_info and matched_info.get("high_risk", False))
        or any(k in target_key for k in HIGH_RISK_KEYWORDS)
        or any(k in desired for k in ("unlock", "disarm"))
    )
    if is_high_risk and desired in ("unlock", "disarm", "on", "open") and not confirm:
        record_audit_event(
            "iot_security",
            "high_risk_confirmation_required",
            "blocked",
            {"device": matched_id or device, "requested_state": desired},
        )
        return {
            "status": "confirmation_required",
            "device": matched_id or device,
            "requested_state": desired,
            "message": (
                f"Security Gate Active: '{matched_id or device}' is a physical access control device. "
                f"Explicit confirmation (confirm=True) is required before unlocking or disarming."
            ),
        }

    if not matched_info:
        record_audit_event("iot", "device_not_found", "Simulated/Unregistered", {"device": device, "state": desired})
        return {
            "status": "simulated",
            "device": device or "unspecified",
            "state": desired,
            "message": (
                f"IoT directive '{desired}' logged for '{device}'. "
                f"(Register its LAN IP in ~/.veronica/iot_devices.json or set HA_URL/HA_TOKEN for live hardware actuation.)"
            ),
        }

    dtype = matched_info.get("type", "homeassistant").lower()
    dev_host = matched_info.get("host", "")

    # 1. Shelly Local HTTP Relay
    if dtype == "shelly" and dev_host:
        if not is_safe_iot_endpoint(dev_host):
            return {"status": "blocked", "message": "Rejected non-LAN IoT endpoint."}
        turn_param = "toggle" if desired == "toggle" else ("on" if desired == "on" else "off")
        url = f"http://{dev_host}/relay/0?turn={turn_param}"
        try:
            with httpx.Client(timeout=2.5) as client:
                resp = client.get(url)
                record_audit_event("iot", f"shelly_{turn_param}", "success", {"device": matched_id, "http": resp.status_code})
                return {"status": "success", "device": matched_info["name"], "state": turn_param, "protocol": "shelly_lan"}
        except Exception as exc:
            record_audit_event("iot", f"shelly_{turn_param}", "offline", {"device": matched_id, "error": str(exc)})
            return {"status": "offline", "device": matched_info["name"], "state": turn_param, "message": f"{matched_info['name']} at {dev_host} is currently unreachable on LAN."}

    # 2. WLED Local HTTP API
    if dtype == "wled" and dev_host:
        if not is_safe_iot_endpoint(dev_host):
            return {"status": "blocked", "message": "Rejected non-LAN IoT endpoint."}
        wled_t = "2" if desired == "toggle" else ("1" if desired == "on" else "0")
        url = f"http://{dev_host}/win&T={wled_t}"
        try:
            with httpx.Client(timeout=2.5) as client:
                resp = client.get(url)
                record_audit_event("iot", f"wled_{desired}", "success", {"device": matched_id, "http": resp.status_code})
                return {"status": "success", "device": matched_info["name"], "state": desired, "protocol": "wled_lan"}
        except Exception as exc:
            record_audit_event("iot", f"wled_{desired}", "offline", {"device": matched_id, "error": str(exc)})
            return {"status": "offline", "device": matched_info["name"], "state": desired, "message": f"{matched_info['name']} at {dev_host} is unreachable on LAN."}

    # 3. Home Assistant REST Bridge
    if dtype == "homeassistant" and ha_url and ha_token:
        if not is_safe_iot_endpoint(ha_url):
            return {"status": "blocked", "message": "Home Assistant URL must be on a private LAN or .local host."}
        entity_id = matched_info.get("entity_id", f"light.{matched_id}")
        domain = entity_id.split(".")[0]
        service = "toggle" if desired == "toggle" else ("turn_on" if desired == "on" else "turn_off")
        if domain == "lock":
            service = "unlock" if desired in ("unlock", "on") else "lock"
        url = f"{ha_url.rstrip('/')}/api/services/{domain}/{service}"
        try:
            with httpx.Client(timeout=3.5) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"},
                    json={"entity_id": entity_id},
                )
                record_audit_event("iot", f"ha_{domain}_{service}", "success", {"entity_id": entity_id, "http": resp.status_code})
                return {"status": "success", "device": matched_info["name"], "state": desired, "protocol": "home_assistant"}
        except Exception as exc:
            record_audit_event("iot", f"ha_{domain}_{service}", "offline", {"entity_id": entity_id, "error": str(exc)})
            return {"status": "offline", "device": matched_info["name"], "state": desired, "message": f"Home Assistant hub unreachable: {exc}"}

    record_audit_event("iot", f"dispatch_{desired}", "standby", {"device": matched_id})
    return {
        "status": "standby",
        "device": matched_info["name"],
        "state": desired,
        "message": f"Directive '{desired}' queued for {matched_info['name']}. Connect Home Assistant (HA_URL / HA_TOKEN) or set LAN IP in ~/.veronica/iot_devices.json for live actuation.",
    }
