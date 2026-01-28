from pydantic import BaseModel


class PlayRecordRequest(BaseModel):
    record_file: str
    camera_channel: str = None
    event_channel: str = None
    box_channel: str = None
    points_channel: str = None
