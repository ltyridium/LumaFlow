from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


TLV_HEAD = bytes((0xEB, 0x90))
TLV_TAIL = 0xED
CMD_STREAM = 0xD8
CMD_AUTH = 0xE0
STREAM_PAYLOAD_LENGTH = 20


@dataclass(frozen=True)
class AuthLicense:
    ble_mac: bytes
    expire_time: int
    signature: bytes


def format_mac(mac_bytes: bytes) -> str:
    return ":".join(f"{byte:02X}" for byte in mac_bytes)


def format_duration(delta_seconds: int) -> str:
    total_minutes = max(0, abs(int(delta_seconds)) // 60)
    days, rem_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem_minutes, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if days or hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def normalize_mac(mac_text: str) -> bytes:
    cleaned = "".join(ch for ch in mac_text.strip() if ch.isalnum())
    if len(cleaned) != 12:
        raise ValueError("BLE MAC must contain exactly 12 hex digits.")
    try:
        mac_bytes = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("BLE MAC must be valid hexadecimal.") from exc
    if len(mac_bytes) != 6:
        raise ValueError("BLE MAC must decode to 6 bytes.")
    return mac_bytes


def parse_auth_lic(lic_text: str) -> AuthLicense:
    parts = [part.strip() for part in lic_text.strip().split("|")]
    if len(parts) != 3:
        raise ValueError("AUTH LIC must use the format MAC|expire_time|signature_hex.")

    mac_bytes = normalize_mac(parts[0])

    try:
        expire_time = int(parts[1], 10)
    except ValueError as exc:
        raise ValueError("AUTH LIC expire_time must be a decimal Unix timestamp.") from exc
    if expire_time < 0 or expire_time > 0xFFFFFFFF:
        raise ValueError("AUTH LIC expire_time must fit in uint32.")

    signature_hex = "".join(parts[2].split())
    if len(signature_hex) % 2 != 0:
        raise ValueError("AUTH LIC signature_hex must have an even number of hex digits.")
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError as exc:
        raise ValueError("AUTH LIC signature_hex must be valid hexadecimal.") from exc
    if not 1 <= len(signature) <= 72:
        raise ValueError("AUTH LIC signature length must be between 1 and 72 bytes.")

    return AuthLicense(ble_mac=mac_bytes, expire_time=expire_time, signature=signature)


def describe_auth_lic(lic_text: str, now: int | None = None) -> dict[str, object]:
    current_time = int(datetime.now().timestamp()) if now is None else int(now)
    empty_info = {
        "valid": False,
        "empty": True,
        "device_mac": "--",
        "expire_at": "--",
        "validity": "--",
        "signature": "--",
        "status": "No LIC loaded",
        "is_expired": False,
    }

    if not lic_text or not lic_text.strip():
        return empty_info

    try:
        license_data = parse_auth_lic(lic_text)
    except ValueError as exc:
        return {
            **empty_info,
            "empty": False,
            "status": f"Invalid LIC: {exc}",
        }

    expire_dt = datetime.fromtimestamp(license_data.expire_time)
    delta_seconds = license_data.expire_time - current_time
    is_expired = delta_seconds < 0
    validity = (
        f"Expired {format_duration(delta_seconds)}"
        if is_expired
        else f"Remaining {format_duration(delta_seconds)}"
    )

    return {
        "valid": True,
        "empty": False,
        "device_mac": format_mac(license_data.ble_mac),
        "expire_at": expire_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "validity": validity,
        "signature": f"{len(license_data.signature)} bytes",
        "status": "Ready",
        "is_expired": is_expired,
    }


def build_tlv_frame(cmd: int, payload: bytes) -> bytes:
    if not 0 <= cmd <= 0xFF:
        raise ValueError("Command must fit in a single byte.")
    if len(payload) > 127:
        raise ValueError("TLV payload length cannot exceed 127 bytes.")

    length = 1 + len(payload)
    checksum = (length + cmd + sum(payload)) & 0xFF
    return TLV_HEAD + bytes((length, cmd)) + payload + bytes((checksum, TLV_TAIL))


def build_stream_payload(frame: Mapping[str, object]) -> bytes:
    payload = bytearray()
    for index in range(10):
        func = int(frame[f"ch{index}_function"])
        red = int(frame[f"ch{index}_red"])
        green = int(frame[f"ch{index}_green"])
        blue = int(frame[f"ch{index}_blue"])

        for value, label in ((func, "function"), (red, "red"), (green, "green"), (blue, "blue")):
            if not 0 <= value <= 0x0F:
                raise ValueError(f"Channel {index} {label} value must be in range 0..15.")

        payload.append(((func & 0x0F) << 4) | (red & 0x0F))
        payload.append(((green & 0x0F) << 4) | (blue & 0x0F))

    if len(payload) != STREAM_PAYLOAD_LENGTH:
        raise ValueError("STREAM payload must be exactly 20 bytes.")
    return bytes(payload)


def build_stream_frame(frame: Mapping[str, object]) -> bytes:
    return build_tlv_frame(CMD_STREAM, build_stream_payload(frame))


def build_auth_payload(host_time: int, expire_time: int, signature: bytes) -> bytes:
    if not 0 <= host_time <= 0xFFFFFFFF:
        raise ValueError("host_time must fit in uint32.")
    if not 0 <= expire_time <= 0xFFFFFFFF:
        raise ValueError("expire_time must fit in uint32.")
    if host_time > expire_time:
        raise ValueError("AUTH LIC has already expired.")
    if not 1 <= len(signature) <= 72:
        raise ValueError("AUTH signature length must be between 1 and 72 bytes.")

    payload = bytearray()
    payload.extend(host_time.to_bytes(4, "little"))
    payload.extend(expire_time.to_bytes(4, "little"))
    payload.append(len(signature))
    payload.extend(signature)
    return bytes(payload)


def build_auth_frame(lic_text: str, host_time: int) -> bytes:
    license_data = parse_auth_lic(lic_text)
    payload = build_auth_payload(host_time, license_data.expire_time, license_data.signature)
    return build_tlv_frame(CMD_AUTH, payload)
