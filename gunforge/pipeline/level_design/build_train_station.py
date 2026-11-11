"""Assemble the four train-station battles and workbench arrival into one session."""
from build_green_car import GreenCar
from build_lantern_pullback import LanternPullback
from build_night_market import NightMarket
from build_platform import Platform
from build_waiting_room import WaitingRoom
from compiler import DEFAULT_CACHE, ROOT, compile_source, write_build
from freeze_baseline import dump
from versions import publish, resolve


STOPS = (WaitingRoom, Platform, GreenCar, LanternPullback)


def build(*, package="paper.train_station", configure_stop=None):
    station = NightMarket()
    station.source.update(id=package, seed=434)
    station.presentation.update(subtitle="第三关 · 火车站", instructions="穿过火车站 · 净化灯座 · 抵达工作台",
                                stations=["候车室", "站台", "绿皮车厢", "灯座", "爷爷的工作台"])
    station.presentation["labels"].update(result_success="抵达工作台", result_failure="灯芯耗尽")

    revisions = {}
    for index, constructor in enumerate(STOPS, 1):
        stop = constructor()
        source = stop.author()
        revisions[source["id"]] = publish(source).parent.name
        if configure_stop is not None:
            configure_stop(stop)
        last = index == len(STOPS)
        # Keep the intermediate cut in its own renderer section while the workbench is station five.
        indices = {stop.stage: index, "pullback": None, "workbench": index + 1} if last else None
        station.append(stop.stage, index, f"{stop.stage}.complete", source,
                       continue_after=not last, station_indices=indices)

    entry = publish(station.source)
    _, verified, manifest = resolve(station.source["id"], entry.parent.name)
    compiled = compile_source(verified, source_manifest=manifest)
    output = write_build(compiled, DEFAULT_CACHE)
    review = package.removeprefix("paper.") + "_build.json"
    dump(ROOT / "gunforge/level_design/reviews" / review, {"source": str(entry),
         "source_revision": compiled["source_revision"], "build_id": compiled["build_id"], "compiled": str(output),
         "state": "candidate_not_adopted", "component_revisions": revisions})
    print(output)


if __name__ == "__main__":
    build()
