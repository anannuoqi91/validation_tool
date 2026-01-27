import argparse
import os
from cyber_record.record import Record


def arg_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=str, required=True,
                        help="record data directory or record file path")
    args = parser.parse_args()
    return args


def get_info_with_return(path_record):
    out = {}
    try:
        record = Record(path_record)
        out["start_time"] = record.get_start_time()
        out["end_time"] = record.get_end_time()
        out["channels"] = []
        channels = record.get_channel_cache()
        for channel in channels:
            out["channels"].append({
                "name": channel.name,
                "type": channel.message_type,
                "count": channel.message_number
            })
    except:
        raise Exception(f"get info {path_record} failed")
    return out


def get_channel_info(record):
    out = {}
    channels = record.get_channel_cache()
    for channel in channels:
        out[channel.name] = {
            "type": channel.message_type,
            "count": channel.message_number
        }

    return out


def get_info(path_record):
    print(f"")
    print(f"+++++++++++++++++++++++++++++++++++++++++++")
    print(f"File Path: {path_record}")
    try:
        record = Record(path_record)
        print(f"Start Time: {record.get_start_time()}")
        print(f"End Time: {record.get_end_time()}")
        print(f"Channels: ")
        channels = record.get_channel_cache()
        for channel in channels:
            print(
                f"    name: {channel.name}\n"
                f"        type: {channel.message_type}\n"
                f"        count: {channel.message_number}")
    except:
        print(f"get info {path_record} failed")
    print(f"+++++++++++++++++++++++++++++++++++++++++++")


if __name__ == '__main__':
    args = arg_parse()
    if not os.path.exists(args.record):
        raise FileNotFoundError(f"record {args.record} not exists")
    if os.path.isdir(args.record):
        for i in os.listdir(args.record):
            path_record = os.path.join(args.record, i)
            get_info(path_record)
    else:
        get_info(args.record)
