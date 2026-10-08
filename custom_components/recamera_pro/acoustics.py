"""AcousticsLab inference stream decoder for the new reCamera Pro."""

from __future__ import annotations

import struct
from dataclasses import dataclass


MAX_PROTOBUF_BYTES = 64 * 1024


class AcousticsDecodeError(ValueError):
    """Raised when an inference frame is malformed."""


@dataclass(slots=True)
class AcousticsScore:
    """One TopK classification result."""

    class_idx: int
    label: str
    probability: float


@dataclass(slots=True)
class AcousticsInference:
    """Decoded AcousticsLab InferenceFrame."""

    sequence: int
    capture_time_us: int | None
    publish_time_us: int | None
    head_id: str | None
    head_version: int | None
    scores: list[AcousticsScore]


def _read_varint(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(payload) and shift <= 63:
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise AcousticsDecodeError("invalid_varint")


def _read_fields(payload: bytes):
    offset = 0
    while offset < len(payload):
        key, offset = _read_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number == 0:
            raise AcousticsDecodeError("invalid_field_number")
        if wire_type == 0:
            value, offset = _read_varint(payload, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(payload):
                raise AcousticsDecodeError("truncated_fixed64")
            value = payload[offset:end]
            offset = end
        elif wire_type == 2:
            length, offset = _read_varint(payload, offset)
            end = offset + length
            if end > len(payload):
                raise AcousticsDecodeError("truncated_length_delimited")
            value = payload[offset:end]
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(payload):
                raise AcousticsDecodeError("truncated_fixed32")
            value = payload[offset:end]
            offset = end
        else:
            raise AcousticsDecodeError(f"unsupported_wire_type:{wire_type}")
        yield field_number, wire_type, value


def _decode_top_k(payload: bytes) -> AcousticsScore:
    class_idx = 0
    label = ""
    probability = 0.0
    for field_number, wire_type, value in _read_fields(payload):
        if field_number == 1 and wire_type == 0:
            class_idx = int(value)
        elif field_number == 2 and wire_type == 2:
            label = value.decode("utf-8", errors="replace")
        elif field_number == 3 and wire_type == 5:
            probability = float(struct.unpack("<f", value)[0])
    return AcousticsScore(
        class_idx=class_idx,
        label=label,
        probability=max(0.0, min(1.0, probability)),
    )


def decode_inference_envelope(payload: bytes) -> AcousticsInference | None:
    """Decode a WS binary Envelope and return its inference payload.

    WebSocket frames contain the protobuf Envelope directly. The four-byte
    little-endian size prefix is used only by the local Unix socket.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_PROTOBUF_BYTES:
        raise AcousticsDecodeError("invalid_payload_size")

    inference_payload = None
    for field_number, wire_type, value in _read_fields(payload):
        if field_number == 11 and wire_type == 2:
            inference_payload = value
            break
    if inference_payload is None:
        return None

    sequence = 0
    capture_time_us = None
    publish_time_us = None
    head_id = None
    head_version = None
    scores: list[AcousticsScore] = []
    for field_number, wire_type, value in _read_fields(inference_payload):
        if field_number == 1 and wire_type == 0:
            sequence = int(value)
        elif field_number == 2 and wire_type == 0:
            capture_time_us = int(value)
        elif field_number == 4 and wire_type == 2:
            scores.append(_decode_top_k(value))
        elif field_number == 5 and wire_type == 2:
            head_id = value.decode("utf-8", errors="replace")
        elif field_number == 7 and wire_type == 0:
            publish_time_us = int(value)
        elif field_number == 9 and wire_type == 0:
            head_version = int(value)

    return AcousticsInference(
        sequence=sequence,
        capture_time_us=capture_time_us,
        publish_time_us=publish_time_us,
        head_id=head_id,
        head_version=head_version,
        scores=scores,
    )
