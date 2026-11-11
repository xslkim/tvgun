"""Build a train-station candidate with dedicated light-gated eyes."""
import argparse
from pathlib import Path

from PIL import Image

from build_cinema import ART as CINEMA_ART
from build_train_station import build
from build_train_stop import ART, CROW
from compiler import compile_source, read, write_build


EYES = ART / "variants/hardened_eyes/eyes.png"
PACKAGE = "paper.train_station_hardened"


def prepare_eyes():
    crow = read(CROW / "enemy.json")
    entry = crow["files"]["core_hardened"]
    with Image.open(CROW / entry["file"]) as source:
        tint = tuple(crow["hardened_eye_material"]["eye_tint_rgb"])
        warm = Image.new("RGBA", source.size, tint)
        warm.putalpha(source.getchannel("A"))
    EYES.parent.mkdir(parents=True, exist_ok=True)
    warm.save(EYES)
    return entry


def attach_eyes(stop, crow_entry):
    for name, actor in stop.entities.items():
        if "mask_permission" not in actor:
            continue
        if name == f"{stop.stage}.crow":
            part = actor["parts"]["stamp"]
            x, y = (value / 1024 for value in crow_entry["crop_origin"])
            width, height = (value / 1024 for value in crow_entry["size"])
        elif name == f"{stop.stage}.umbrella":
            part = actor["parts"]["seal"]
            with Image.open(CINEMA_ART / "actors/ink_umbrella/weak.png") as stamp:
                left, top, right, bottom = stamp.getbbox()
                width, height = 56 / actor["width"], 14 / actor["height"]
                x = (left + right) / (2 * stamp.width) - width / 2
                y = (top + bottom) / (2 * stamp.height) - height / 2
        else:
            continue
        part["hardened_visual"] = {"resource": stop.image(EYES), **{
            key: round(value * 1024) / 1024
            for key, value in zip(("x", "y", "width", "height"), (x, y, width, height))
        }}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-builds", type=Path)
    args = parser.parse_args()
    crow_entry = prepare_eyes()

    def configure(stop):
        attach_eyes(stop, crow_entry)
        if args.probe_builds:
            path = write_build(compile_source(stop.source), args.probe_builds)
            (args.probe_builds / f"{stop.stage}.txt").write_text(str(path), encoding="utf-8")

    build(package=PACKAGE, configure_stop=configure)


if __name__ == "__main__":
    main()
