from __future__ import annotations

from pprint import pprint

from obsws_python import ReqClient


def attrs(obj: object) -> dict[str, object]:
    names = getattr(obj, "attrs", None)
    if isinstance(names, list):
        return {name: getattr(obj, name, None) for name in names}
    if callable(names):
        return names()
    return {name: getattr(obj, name) for name in dir(obj) if not name.startswith("_") and name != "attrs"}


def main() -> int:
    client = ReqClient(host="localhost", port=4455, password="123456", timeout=5)
    print("connected_to_obs=true")
    for name in [
        "get_version",
        "get_video_settings",
        "get_record_status",
        "get_profile_list",
        "get_output_list",
        "get_scene_list",
    ]:
        print(f"\n## {name}")
        try:
            result = getattr(client, name)()
            pprint(attrs(result), width=140)
        except Exception as exc:
            print(f"ERROR {type(exc).__name__}: {exc}")
    for output_name in ["adv_file_output", "simple_file_output", "ReplayBuffer"]:
        print(f"\n## get_output_settings {output_name}")
        try:
            result = client.get_output_settings(output_name)
            pprint(attrs(result), width=140)
        except Exception as exc:
            print(f"ERROR {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
