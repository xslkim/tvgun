extends SceneTree
## Play the campaign through the shared input queue without resetting the session.

const Loader = preload("res://core/level_loader.gd")
const Session = preload("res://core/level_session.gd")
const STAGES = ["alley", "stall", "video_shop", "footbridge", "plaza"]
const CINEMA_STAGES = ["ticket_office", "poster_hall", "auditorium", "projection_booth", "screen_stage"]
var model
var stages: Array = []
var combined := false
var session = Session.new()
var failures: Array[String] = []
var reached: Array[int] = []
var handoffs: Array = []
var viewport: SubViewport
var captures := ""
var profile_path := ""
var profile_last_frame_us := 0
var profile_open_us := 0
var profile_samples: Array[Dictionary] = []
var profile_texture_sizes: Dictionary = {}
var screen_entry_tick := -1
var failure_retries: Array[Dictionary] = []
var previous_pose: Array = []
var previous_point: Variant
var checked_old_shot := false
var chapter_pose: Array = []
var chapter_point: Variant
var checked_chapter_shot := false
var chapter_tick := -1
var reloads := 0

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	if not value:
		failures.append(label)

func station() -> int:
	return int(model.level.sections.get(model.current_section, {}).get("station", 0))

func carried() -> Dictionary:
	return {"lives": model.resources.lives, "ammo": model.resources.ammo, "score": model.resources.score,
		"rescued": model.resources.rescued, "shots": model.shots}

func aim(item, pose: Array) -> Variant:
	var area: Rect2 = item.bounds().intersection(Rect2(0, 0, 1776, 936))
	var middle := area.get_center()
	if model.resolver.exact(middle, pose).get("id") == item.id:
		return middle
	for y in range(ceili(area.position.y), floori(area.end.y), 7):
		for x in range(ceili(area.position.x), floori(area.end.x), 7):
			var point := Vector2(x, y)
			if model.resolver.exact(point, pose).get("id") == item.id:
				return point
	return null

func capture(name: String) -> void:
	if captures.is_empty() or viewport == null:
		return
	await process_frame
	await RenderingServer.frame_post_draw
	check(viewport.get_texture().get_image().save_png(captures.path_join(name + ".png")) == OK, "capture " + name)

func prepare_texture_accounting() -> void:
	var presentation: Dictionary = model.level.presentation
	var stage_resources: Dictionary = {}
	for layer in presentation.layers.values():
		stage_resources[layer.resource] = true
	var lamp_wipes: Dictionary = presentation.get("bottom_wipes", {})
	for id in model.level.entities:
		var entity: Dictionary = model.level.entities[id]
		var beam: bool = id.begins_with("cinema.projector_") and (id.ends_with(".dark") or id.ends_with(".warm"))
		if entity.template != "activation_source" and not lamp_wipes.has(id) and not beam:
			continue
		stage_resources[entity.get("resource", "")] = true
		for part in entity.get("parts", {}).values():
			stage_resources[part.resource] = true
	for id in model.images:
		var image: Image = model.images[id]
		var bytes := image.get_data_size()
		profile_texture_sizes[image.get_instance_id()] = Vector2i(bytes, 0) if stage_resources.has(id) else Vector2i(0, bytes)

func sample_rendered_frame() -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	var frame_us := Time.get_ticks_usec()
	if profile_last_frame_us > 0:
		var scene = model.render_scene
		var resident := Vector2i.ZERO
		for id in scene.textures:
			resident += profile_texture_sizes[id]
		var preloaded := Vector2i.ZERO
		for id in scene.preloaded_textures:
			preloaded += profile_texture_sizes[id]
		profile_samples.append({
			"tick": model.tick,
			"section": model.current_section,
			"station": station(),
			"frame_us": frame_us - profile_last_frame_us,
			"process_us": roundi(Performance.get_monitor(Performance.TIME_PROCESS) * 1000000),
			"texture_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
			"video_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
			"draw_calls": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
			"cached_textures": scene.textures.size(),
			"stage_texture_bytes": resident.x,
			"actor_prop_texture_bytes": resident.y,
			"preloaded_section": scene.preloaded_section,
			"preloaded_textures": scene.preloaded_textures.size(),
			"preloaded_stage_texture_bytes": preloaded.x,
			"preloaded_actor_prop_texture_bytes": preloaded.y,
			"texture_upload_count": scene.upload_count,
			"texture_upload_us": scene.upload_us,
		})
	profile_last_frame_us = frame_us

func write_profile() -> void:
	var report := FileAccess.open(profile_path, FileAccess.WRITE)
	check(report != null, "write frame profile")
	if report == null:
		return
	var sweep_spawns: Array = model.trace.filter(func(entry):
		return entry.topic == "entity.spawned" and entry.entity.begins_with("cinema.sweep_tape_"))
	check(not combined or sweep_spawns.size() == 3, "profile exercises all three projector spawns")
	report.store_string(JSON.stringify({
		"build_id": model.build.build_id,
		"gpu": RenderingServer.get_video_adapter_name(),
		"rendering_method": RenderingServer.get_current_rendering_method(),
		"viewport": [viewport.size.x, viewport.size.y],
		"open_us": profile_open_us,
		"screen_sweep_spawns": sweep_spawns,
		"samples": profile_samples,
	}) + "\n")

func check_texture_restart() -> void:
	if combined:
		session.seek(screen_entry_tick - 20)
		await process_frame
		await RenderingServer.frame_post_draw
		check(station() == 9 and model.render_scene.preloaded_section == "cinema.screen_stage"
			and not model.render_scene.preloaded_textures.is_empty(), "seeking into the handoff preloads the screen")
		session.seek(screen_entry_tick - 120)
		await process_frame
		await RenderingServer.frame_post_draw
		check(station() == 9 and model.render_scene.preloaded_textures.is_empty(),
			"seeking back before the hold releases the pending screen textures")
		session.seek(screen_entry_tick - 20)
		await process_frame
		await RenderingServer.frame_post_draw
	session.start()
	await process_frame
	await RenderingServer.frame_post_draw
	check(station() == 1 and model.resources.lives == 5, "restart resets to the alley")
	var visible: Dictionary = {}
	for item in model.visual_items():
		visible[item.image.get_instance_id()] = true
	var cached: Dictionary = model.render_scene.textures
	check(cached.size() == visible.size() and cached.keys().all(func(id): return visible.has(id)),
		"restart retains only textures used by the alley opening")
	check(model.render_scene.preloaded_textures.is_empty(), "restart clears pending textures")

func retry_from_defeat(expected_station: int) -> void:
	var defeated := carried()
	var defeat_tick: int = model.tick
	check(station() == expected_station and model.phase == "result" and model.result == "overrun"
		and model.resources.lives == 0, "station %d reaches the defeated result" % expected_station)
	if model.phase != "result":
		return
	session.submit(model.geometry())
	check(session.enqueue("SHOT", Vector2(2, 2)) and session.enqueue("RELOAD"), "submit controls at result")
	session.step()
	check(session.last_results.size() == 2 and session.last_results.all(func(reply): return reply.get("reason") == "not_running")
		and carried() == defeated, "result rejects shooting and reload without changing counters")
	session.start()
	var restarted := carried()
	check(station() == 1 and model.phase == "running" and model.tick == 0
		and model.resources == model.level.initial_resources and model.shots == 0,
		"retry returns to the alley with initial player and station counters")
	check(not model.entities["flow.cinema"].active and session.submission.is_empty()
		and session.queue.pending.is_empty() and session.tape.is_empty(), "retry clears prior station and input state")
	while model.phase == "running" and not model.input_enabled and model.tick < 300:
		session.step()
	session.submit(model.geometry())
	check(session.enqueue("SHOT", Vector2(2, 2)), "retry accepts a freshly submitted shot")
	session.step()
	check(model.shots == 1 and model.resources.ammo == restarted.ammo - 1, "fresh shot consumes exactly one round")
	failure_retries.append({"station": expected_station, "defeat_tick": defeat_tick, "before_retry": defeated,
		"after_retry": restarted, "first_shot": carried()})

func check_failure_retries() -> void:
	var ticket: Dictionary = handoffs[4]
	session.seek(ticket.tick)
	check(station() == 6 and model.resources.lives == 4, "reuse the played route into the cinema")
	# An actual command branches from the saved route so the prior winning shots are no longer replayed.
	check(session.enqueue("RELOAD"), "branch the recorded playthrough at the ticket office")
	while model.phase == "running" and model.resources.lives > 2 and model.tick < ticket.tick + 1000:
		session.step()
	check(station() == 6 and model.resources.lives == 2, "take both ticket-office attacks")
	while station() == 6 and model.phase == "running" and model.tick < ticket.tick + 1600:
		queue_action(6)
		session.step()
	var poster_end: int = model.tick + 1000
	while model.phase == "running" and model.tick < poster_end:
		session.step()
	retry_from_defeat(7)
	session.start()
	while model.phase == "running" and model.tick < 6000:
		session.step()
	retry_from_defeat(1)

func handle_entry(index: int, previous: int, before: Dictionary) -> void:
	reached.append(index)
	var name: String = stages[index - 1]
	var marker := "flow.cinema" if index > 5 else "flow." + name
	check(model.entities[marker].active, "current station is active")
	if previous > 0:
		var old: String = stages[previous - 1]
		var prefix := "cinema." + old + "." if previous > 5 else old + "."
		check(carried() == before, "%s preserves player counters across the handoff" % name)
		if previous <= 5:
			check(not model.entities["flow." + old].active, "prior stage events are deactivated")
		check(not model.visual_items().any(func(item): return item.id.begins_with(prefix) or item.id.begins_with("layer." + prefix)),
			"prior targets and layers are removed at the cut")
		handoffs.append({"station": name, "tick": model.tick, "counters": carried()})
	if index == 2:
		check(model.resources["alley.purified"] > 0 and model.resources["stall.purified"] == 0, "stall starts with its own wave counter")
	if index == 6:
		check(chapter_tick >= 0 and model.tick - chapter_tick == 90 and not model.entities["dragon.anchor"].active,
			"chapter transition removes the dragon and opens the ticket office after 1.5 seconds")
	if index == 10:
		screen_entry_tick = model.tick
	await capture("station_%d_%s" % [index, name])

func queue_action(index: int) -> bool:
	if not model.input_enabled or model.tick < model.next_shot or model.reload_at >= 0:
		return false
	if index == 1 and model.resources.lives == 5 and model.tick < 1260:
		return false # Leave the first attack live so the handoff has a spent life to carry.
	if not profile_path.is_empty() and index == 10 and model.tick - screen_entry_tick < 315:
		return false # Let all three projectors sweep and spawn before clearing the screen.
	if model.resources.ammo == 0:
		if session.enqueue("RELOAD"):
			reloads += 1
		return false
	if index == 2 and not checked_old_shot and previous_point != null:
		session.submit(previous_pose)
		return session.enqueue("SHOT", previous_point)
	if index == 6 and not checked_chapter_shot and chapter_point != null:
		session.submit(chapter_pose)
		return session.enqueue("SHOT", chapter_point)
	var pose: Array = model.geometry()
	var lamp_item = null
	for item in pose:
		if item.kind not in ["primary", "weak"]:
			continue
		if model.entities[item.id].template == "activation_source":
			if index > 1 and model.tick >= model.entities[item.id].next_activation:
				lamp_item = item
			continue
		var point = aim(item, pose)
		if point != null:
			if combined and item.id == "dragon.mouth":
				chapter_pose = pose
				chapter_point = point
			session.submit(pose)
			session.enqueue("SHOT", point)
			return false
	if lamp_item != null:
		var point = aim(lamp_item, pose)
		if point != null:
			session.submit(pose)
			session.enqueue("SHOT", point)
	return false

func play() -> void:
	var current := station()
	check(current == 1, "campaign begins at the alley")
	if current != 1:
		return
	await handle_entry(current, 0, {})
	if not profile_path.is_empty():
		await sample_rendered_frame()
	var showed_dragon := false
	while model.phase == "running" and model.tick < 16000:
		if current == 1 and model.tick == 5500:
			previous_pose = model.geometry()
			for item in previous_pose:
				if item.id == "alley.lamp":
					previous_point = aim(item, previous_pose)
					break
		if current == 5 and not showed_dragon and model.entities["dragon.anchor"].active:
			showed_dragon = true
			await capture("station_5_dragon")
		var before := carried()
		var stale := queue_action(current)
		session.step()
		if stale:
			if current == 2:
				checked_old_shot = true
			else:
				checked_chapter_shot = true
			check(not session.last_results.is_empty() and session.last_results[0].get("reason") == "target_inactive",
				"a submitted shot from the previous station cannot hit after the handoff")
		var next := station()
		if combined and next == 0 and current == 5 and chapter_tick < 0:
			chapter_tick = model.tick
			check(model.current_section == "story.cinema_intro" and model.phase == "running" and not model.input_enabled,
				"dragon clear shows the cinema transition without ending the session")
			check(model.entities["dragon.anchor"].active and not model.entities["flow.cinema"].active,
				"chapter transition keeps the purified dragon visible until the cut")
			await capture("cinema_transition")
		if next > 0 and next != current:
			await handle_entry(next, current, before)
			current = next
		if not profile_path.is_empty():
			await sample_rendered_frame()
	check(reached == range(1, stages.size() + 1), "all stations reached in order")
	var final_target := "cinema.shadow_core" if combined else "dragon.mouth"
	check(model.result == "clear" and model.entities[final_target].health <= 0, "final boss ends the campaign")
	var rescues := 5 if combined else 2
	check(model.resources.rescued == rescues and model.resources["stall.purified"] == 6 and model.resources.lives < 5,
		"two rescues, local stall progress and damage survive the full run")
	check(checked_old_shot and reloads > 0, "old pose and shared magazine were exercised")
	if combined:
		check(checked_chapter_shot, "chapter handoff rejects the stale dragon pose")
	await capture("lantern_city_clear" if combined else "night_market_clear")

func run() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var pair := arg.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	profile_path = args.get("--profile", "")
	if not profile_path.is_empty() and DisplayServer.get_name() == "headless":
		push_error("Frame profiling needs a graphics display")
		quit(2)
		return
	var open_started := Time.get_ticks_usec()
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	model = Loader.open(compiled, args.get("--assets", ""))
	profile_open_us = Time.get_ticks_usec() - open_started
	if model == null:
		quit(2)
		return
	combined = model.level.id == "paper.lantern_city"
	stages = STAGES + CINEMA_STAGES if combined else STAGES
	captures = args.get("--captures", "")
	if not profile_path.is_empty() or (not captures.is_empty() and DisplayServer.get_name() != "headless"):
		if not captures.is_empty() and DirAccess.make_dir_recursive_absolute(captures) != OK:
			quit(2)
			return
		viewport = SubViewport.new()
		viewport.size = Vector2i(1776, 936)
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		model.mount(viewport)
		if not profile_path.is_empty():
			model.render_scene.measure_uploads = true
			prepare_texture_accounting()
			root.size = Vector2i(1280, 720)
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
			var preview := TextureRect.new()
			preview.texture = viewport.get_texture()
			preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			preview.size = Vector2(root.size)
			root.add_child(preview)
	session.setup(model)
	await play()
	var outcome := {"build_id": model.build.build_id,
		"gpu_capture": viewport != null and not captures.is_empty(), "reached": reached, "handoffs": handoffs, "reloads": reloads,
		"end_tick": model.tick, "counters": carried(), "result": model.result, "chapter_transition_tick": chapter_tick}
	if not profile_path.is_empty():
		write_profile()
		await check_texture_restart()
		outcome["texture_restart_checked"] = true
	if args.get("--failure-retry", "") == "true":
		check(combined and reached.size() == 10, "failure and retry fixture requires the two-level candidate")
		if combined and reached.size() == 10:
			check_failure_retries()
			outcome["failure_retries"] = failure_retries
	outcome["passed"] = failures.is_empty()
	outcome["failures"] = failures
	print(JSON.stringify(outcome))
	quit(0 if failures.is_empty() else 1)
