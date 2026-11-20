#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. The software is
# provided "as is", with no warranty of any type.
"""Registration of generated MedTech DDS types."""

import rti.connextdds as dds

try:
    from MedTech import Device, idl
except ModuleNotFoundError as exc:
    if exc.name != "MedTech":
        raise
    raise RuntimeError(
        "Shared DDS bindings are missing. Run python medtech.py build, then launch through "
        "medtech.py run or add build/<CONNEXTDDS_ARCH>/system/generated/python to PYTHONPATH."
    ) from exc


_registered_types: dict[str, type] = {}

_COMMAND_STATUSES = {
    Device.DeviceCommands.START: Device.DeviceStatuses.ON,
    Device.DeviceCommands.PAUSE: Device.DeviceStatuses.PAUSED,
    Device.DeviceCommands.SHUTDOWN: Device.DeviceStatuses.OFF,
}


def device_status_after_command(command: Device.DeviceCommands) -> Device.DeviceStatuses:
    if not isinstance(command, Device.DeviceCommands):
        raise ValueError(f"Unsupported device command: {command}")
    try:
        return _COMMAND_STATUSES[command]
    except KeyError as exc:
        raise ValueError(f"Unsupported device command: {command}") from exc


def register_type(data_type, name=None):
    type_name = name or idl.get_type_support(data_type).type_name
    registered = _registered_types.get(type_name)
    if registered is not None:
        if registered is not data_type:
            raise ValueError(f"DDS type name {type_name!r} is already registered for {registered}")
        return
    dds.DomainParticipant.register_idl_type(data_type, type_name)
    _registered_types[type_name] = data_type
