from proto.region_pb2 import EventRegionAttribute
from proto.inno_event_pb2 import VolumeFunc


def handle_event_region_attr(event_region_attr):
    def parse_event(serialized_msg, event_class):
        event = event_class()
        event.ParseFromString(serialized_msg)
        return event

    def volume_func(serialized_msg):
        return parse_event(serialized_msg, VolumeFunc)

    switcher = {
        EventRegionAttribute.FLOW_EVENT: volume_func,
    }

    handle = switcher.get(event_region_attr, None)
    return handle
